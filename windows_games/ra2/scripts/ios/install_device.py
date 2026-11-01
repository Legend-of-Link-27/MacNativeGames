#!/usr/bin/env python3
"""Sign the iOS build with your own Apple ID and install it on your iPhone.

    python3 -I scripts/ios/install_device.py [--device "<name>"] [--game game/install [--force]]

A free (Personal Team) Apple ID signs for 7 days, a paid membership for a
year: run this again to renew; the app's Documents (your game files, saves)
are kept. Xcode needs your Apple ID (Xcode > Settings > Accounts), the
iPhone must be paired with this Mac with Developer Mode on, and the first
time, the developer trusted on the phone (Settings > General > VPN &
Device Management).

The provisioning profile comes from a throwaway Xcode project with the same
bundle identifier (xcodebuild -allowProvisioningUpdates registers the device
and the App ID); the app is then re-signed with it. --game copies your own
Red Alert 2 install folder into the app's Documents/RA2 (skipping files the
phone already has at the same size, unless --force; a file the phone has
under another case of the same name is replaced, not doubled); it is never
put in the app bundle.
"""
import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path.home() / 'Library/Caches/WinNativeGames/ios-signing'
# Third-party compatibility layers and installers: not the game.
SKIP = {'ddraw.dll', 'wined3d.dll', 'libwine.dll', 'wsock32.dll'}


def run(cmd, **kw):
    return subprocess.run([str(x) for x in cmd], check=True, **kw)


def out(cmd):
    return subprocess.run([str(x) for x in cmd], check=True, capture_output=True, text=True).stdout


def teams():
    pems = out(['security', 'find-certificate', '-a', '-c', 'Apple Development', '-p'])
    found = set()
    for pem in re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', pems, re.S):
        subject = subprocess.run(['openssl', 'x509', '-noout', '-subject'], input=pem,
                                 capture_output=True, text=True).stdout
        if m := re.search(r'OU\s*=\s*([A-Z0-9]{10})', subject):
            found.add(m.group(1))
    return sorted(found)


def devicectl_json(args):
    with tempfile.NamedTemporaryFile(suffix='.json') as f:
        run(['xcrun', 'devicectl', *args, '--json-output', f.name], capture_output=True)
        return json.load(open(f.name))


def pick_device(name):
    devs = [d for d in devicectl_json(['list', 'devices'])['result']['devices']
            if d.get('hardwareProperties', {}).get('platform') == 'iOS']
    match = [d for d in devs if name in (d['deviceProperties'].get('name'), d['identifier'],
                                         d['hardwareProperties'].get('udid'))] if name else devs
    if len(match) != 1:
        listed = '\n'.join(f"  {d['deviceProperties'].get('name')} "
                           f"({d['hardwareProperties'].get('marketingName')})" for d in devs)
        sys.exit(f'choose the iPhone with --device <name>:\n{listed}' if devs else
                 'no paired iPhone found: connect it, trust this Mac, and turn on Developer Mode')
    return match[0]


def make_profile(team, bundle_id, udid):
    """An empty app with the same bundle identifier; Xcode makes its profile."""
    proj = CACHE / bundle_id
    proj.mkdir(parents=True, exist_ok=True)
    (proj / 'main.m').write_text('int main(void) { return 0; }\n')
    (proj / 'project.yml').write_text(f'''name: Signing
options: {{deploymentTarget: {{iOS: "17.0"}}}}
targets:
  App:
    type: application
    platform: iOS
    sources: [main.m]
    settings:
      GENERATE_INFOPLIST_FILE: YES
      PRODUCT_BUNDLE_IDENTIFIER: {bundle_id}
      DEVELOPMENT_TEAM: {team}
      CODE_SIGN_STYLE: Automatic
''')
    run(['xcodegen', 'generate', '--quiet'], cwd=proj)
    log = proj / 'xcodebuild.log'
    with log.open('w') as f:
        r = subprocess.run(['xcodebuild', '-project', 'Signing.xcodeproj', '-scheme', 'App',
                            '-configuration', 'Debug', '-destination', f'id={udid}',
                            '-derivedDataPath', str(proj / 'derived'), '-allowProvisioningUpdates',
                            '-allowProvisioningDeviceRegistration', 'build'],
                           cwd=proj, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        errors = [l for l in log.read_text(errors='replace').splitlines() if 'error:' in l]
        sys.exit('Xcode could not make a provisioning profile:\n' + '\n'.join(errors[-8:]) +
                 f'\nfull log: {log}')
    app = next((proj / 'derived/Build/Products/Debug-iphoneos').glob('*.app'))
    return app / 'embedded.mobileprovision', app


def signing_identity(signed_app):
    """The SHA-1 of the certificate Xcode signed the throwaway app with."""
    info = subprocess.run(['codesign', '-dvvv', str(signed_app)], capture_output=True, text=True).stderr
    authority = re.search(r'Authority=(Apple Development: [^\n]+)', info).group(1)
    for line in out(['security', 'find-identity', '-v', '-p', 'codesigning']).splitlines():
        if authority in line:
            return line.split()[1]
    sys.exit(f'no signing identity for {authority}')


def profile_plist(path):
    return plistlib.loads(out(['security', 'cms', '-D', '-i', path]).encode())


def sign(app_src, bundle_id, profile_path, identity):
    staging = CACHE / 'staging'
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    app = staging / app_src.name
    shutil.copytree(app_src, app, symlinks=True)
    info_path = app / 'Info.plist'
    info = plistlib.loads(info_path.read_bytes())
    info['CFBundleIdentifier'] = bundle_id
    info_path.write_bytes(plistlib.dumps(info))
    shutil.copy(profile_path, app / 'embedded.mobileprovision')
    prof = profile_plist(profile_path)
    ents = {k: v for k, v in prof['Entitlements'].items()
            if k in ('application-identifier', 'com.apple.developer.team-identifier',
                     'get-task-allow')}
    ent_path = staging / 'app.entitlements'
    ent_path.write_bytes(plistlib.dumps(ents))
    run(['codesign', '--force', '--sign', identity, '--entitlements', ent_path,
         '--generate-entitlement-der', app])
    return app, prof['ExpirationDate']


def device_files(device_id, bundle_id):
    """Size of each file the app's Documents/RA2 holds on the phone."""
    try:
        r = devicectl_json(['device', 'info', 'files', '--device', device_id,
                            '--domain-type', 'appDataContainer', '--domain-identifier', bundle_id,
                            '--subdirectory', 'Documents/RA2'])
    except subprocess.CalledProcessError:
        return {}
    files = r.get('result', {}).get('files', [])
    return {f.get('relativePath', f.get('name')): f.get('size') for f in files}


def copy_game(device_id, bundle_id, game, force=False):
    have = device_files(device_id, bundle_id)
    # The phone's own spelling of each name: the game looks names up in
    # any case, so two spellings of one file must not both be there.
    spelled = {name.lower(): name for name in have}
    for f in sorted(game.iterdir()):
        if not f.is_file() or f.name.lower() in SKIP or f.name.startswith('.'):
            continue
        dest = spelled.get(f.name.lower(), f.name)
        if not force and have.get(dest) == f.stat().st_size:
            continue
        print(f'  copying {f.name} ({f.stat().st_size >> 20} MB)' +
              (f' as {dest}' if dest != f.name else ''))
        for attempt in range(3):
            r = subprocess.run(['xcrun', 'devicectl', 'device', 'copy', 'to', '--device', device_id,
                                '--domain-type', 'appDataContainer', '--domain-identifier', bundle_id,
                                '--source', str(f), '--destination', f'Documents/RA2/{dest}'],
                               capture_output=True, text=True)
            if r.returncode == 0:
                break
            print(f'    retry ({r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "failed"})')
        else:
            sys.exit(f'could not copy {f.name} to the phone')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('app', nargs='?', type=Path,   # IOS_BUILD_DIR as scripts/ios/build_app.sh
                    default=Path(os.environ.get('IOS_BUILD_DIR', ROOT / 'build')) / 'ios/ra2.app')
    ap.add_argument('--device', help='device name, identifier or UDID (as Finder shows it)')
    ap.add_argument('--team', help='Apple team ID, when the keychain has several')
    ap.add_argument('--bundle-id', default='org.winnativegames.ra2')
    ap.add_argument('--game', type=Path, help='your Red Alert 2 install folder, copied to Documents/RA2')
    ap.add_argument('--force', action='store_true',
                    help='with --game: copy every file, even those the phone has at the same size '
                         '(after switching to another install of the same files)')
    a = ap.parse_args()
    if not a.app.is_dir():
        sys.exit(f'{a.app} not found: build it with scripts/ios/build_app.sh')
    ts = [a.team] if a.team else teams()
    if len(ts) != 1:
        sys.exit('choose the team with --team: ' + (', '.join(ts) if ts else
                 'none found; sign in to Xcode with your Apple ID'))
    team = ts[0]
    dev = pick_device(a.device)
    udid, dev_id = dev['hardwareProperties']['udid'], dev['identifier']
    # Free to register on your team; an identifier given with the suffix
    # already (as the phone lists the installed app) is used as it is.
    suffix = '.' + team.lower()
    bundle_id = a.bundle_id if a.bundle_id.endswith(suffix) else a.bundle_id + suffix
    print(f'team {team}, device {dev["deviceProperties"].get("name")}, bundle {bundle_id}')
    profile_path, throwaway = make_profile(team, bundle_id, udid)
    app, expires = sign(a.app, bundle_id, profile_path, signing_identity(throwaway))
    print(f'signed; valid until {expires:%Y-%m-%d %H:%M} (run again to renew)')
    run(['xcrun', 'devicectl', 'device', 'install', 'app', '--device', dev_id, app])
    if a.game:
        copy_game(dev_id, bundle_id, a.game, a.force)
    print('installed. First time: Settings > General > VPN & Device Management > trust the developer.')


if __name__ == '__main__':
    os.environ.setdefault('DEVELOPER_DIR', out(['xcode-select', '-p']).strip())
    main()

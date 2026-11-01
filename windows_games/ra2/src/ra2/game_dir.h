// The player's game directory, as both games' launchers look into it
// (game_dir.cpp).
#pragma once

#include <cstdint>
#include <filesystem>
#include <string>

namespace ra2 {

// The file `name` in the game directory in whatever case it is spelled
// there (the Steam install's names are lower case, the games ask for upper
// case; the runtime's own lookups ignore case like NTFS, but iOS file
// systems do not), else game_dir/name.
std::filesystem::path InGameDir(const std::string& game_dir, const std::string& name);

// The ANSI code page of the game's text (combo box items, edit fields):
// Simplified Chinese (936, GBK) when the game directory holds a Chinese
// string table of the game's own (`csf`: RA2.CSF or RA2MD.CSF, made by
// scripts/make_zh_hans.py; the game reads it before the one in its MIX
// files), else Western European (1252) for the Steam install's English.
uint32_t CodePage(const std::string& game_dir, const char* csf);

}  // namespace ra2

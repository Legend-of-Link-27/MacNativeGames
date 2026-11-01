// The iOS app's entry when it holds both games (CMakeLists.txt,
// WNG_CHOOSER): asks which one to play, then runs it. One game a launch: the
// runtime runs one process image, so another game means starting the app
// again. Without Yuri's Revenge's files in the game folder (gamemd.exe in
// Documents/RA2), Red Alert 2 starts without asking.

#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>

#include <cctype>
#include <cstdlib>
#include <filesystem>
#include <string>

#include "games.h"

namespace {

// Whether the folder holds `name` in some case (iOS file systems care).
bool HasFile(const std::filesystem::path& dir, const std::string& name) {
  auto lower = [](std::string s) {
    for (char& ch : s) ch = char(std::tolower(static_cast<unsigned char>(ch)));
    return s;
  };
  std::error_code ec;
  for (const auto& e : std::filesystem::directory_iterator(dir, ec))
    if (lower(e.path().filename().string()) == lower(name)) return true;
  return false;
}

enum class Game { Ra2, Yr };

Game Choose() {
  const char* home = std::getenv("HOME");
  const std::filesystem::path game_dir = std::string(home ? home : ".") + "/Documents/RA2";
  if (!HasFile(game_dir, "gamemd.exe")) return Game::Ra2;
  const SDL_MessageBoxButtonData buttons[] = {
      {SDL_MESSAGEBOX_BUTTON_RETURNKEY_DEFAULT, int(Game::Ra2), "Red Alert 2"},
      {0, int(Game::Yr), "Yuri's Revenge"},
  };
  SDL_MessageBoxData box{};
  box.flags = SDL_MESSAGEBOX_INFORMATION | SDL_MESSAGEBOX_BUTTONS_LEFT_TO_RIGHT;
  box.title = "Red Alert 2";
  box.message = "Which game?";
  box.numbuttons = int(SDL_arraysize(buttons));
  box.buttons = buttons;
  int picked = int(Game::Ra2);
  if (!SDL_ShowMessageBox(&box, &picked)) return Game::Ra2;
  return picked == int(Game::Yr) ? Game::Yr : Game::Ra2;
}

}  // namespace

int main(int argc, char** argv) {
  return Choose() == Game::Yr ? yr::RunGame(argc, argv) : ra2::RunGame(argc, argv);
}

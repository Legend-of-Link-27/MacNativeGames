// The player's game directory (game_dir.h).

#include "game_dir.h"

#include <cctype>
#include <cstring>
#include <fstream>

namespace ra2 {

std::filesystem::path InGameDir(const std::string& game_dir, const std::string& name) {
  auto lower = [](std::string s) {
    for (char& ch : s) ch = char(std::tolower(static_cast<unsigned char>(ch)));
    return s;
  };
  const std::string want = lower(name);
  std::error_code ec;
  for (const auto& e : std::filesystem::directory_iterator(game_dir, ec))
    if (lower(e.path().filename().string()) == want) return e.path();
  return std::filesystem::path(game_dir) / name;
}

uint32_t CodePage(const std::string& game_dir, const char* csf) {
  constexpr uint32_t kCsfChinese = 9;  // the CSF header's language field
  unsigned char h[24] = {};
  std::ifstream f(InGameDir(game_dir, csf), std::ios::binary);
  if (!f.read(reinterpret_cast<char*>(h), sizeof h) || std::memcmp(h, " FSC", 4) != 0) return 1252;
  const uint32_t language = h[20] | h[21] << 8 | h[22] << 16 | uint32_t(h[23]) << 24;
  return language == kCsfChinese ? 936 : 1252;
}

}  // namespace ra2

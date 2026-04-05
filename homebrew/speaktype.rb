# Homebrew formula for SpeakType
# Install: brew install --cask speaktype (when published)
# Or locally: brew install --formula ./homebrew/speaktype.rb
#
# Note: This formula installs from source using pip and sets up the CLI.
# For the .app bundle, use the cask or DMG installer instead.

class Speaktype < Formula
  desc "AI-powered voice input method for macOS with push-to-talk dictation"
  homepage "https://github.com/speaktype/speaktype"
  url "https://github.com/speaktype/speaktype/archive/refs/tags/v2.0.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256"
  license "MIT"

  depends_on "python@3.10"
  depends_on :macos

  # Ollama is recommended but not required
  # depends_on "ollama" => :recommended

  def install
    # Create virtualenv
    venv = libexec / "venv"
    system "python3.10", "-m", "venv", venv.to_s

    # Install dependencies
    system venv / "bin" / "pip", "install", "--upgrade", "pip"
    system venv / "bin" / "pip", "install", "-r", "requirements.txt"

    # Install the package
    system venv / "bin" / "pip", "install", "-e", "."

    # Create wrapper script
    (bin / "speaktype").write <<~EOS
      #!/bin/bash
      exec "#{venv}/bin/python3" "#{libexec}/main.py" "$@"
    EOS

    # Copy source files
    libexec.install "main.py"
    libexec.install "speaktype"
    libexec.install "requirements.txt"
    libexec.install "setup.py"
  end

  def caveats
    <<~EOS
      SpeakType requires the following macOS permissions:
        - Microphone access (for voice recording)
        - Accessibility access (for text insertion via keyboard simulation)

      Grant these in: System Settings > Privacy & Security

      For AI text polishing, install and run Ollama:
        brew install ollama
        ollama serve &
        ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude

      Start SpeakType:
        speaktype
    EOS
  end

  test do
    assert_match "SpeakType", shell_output("#{bin}/speaktype --help 2>&1", 1)
  end
end

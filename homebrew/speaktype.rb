# Homebrew formula for SpeakType
# Install: brew install --cask speaktype (when published)
# Formula users should place this file in a Homebrew tap before installing.
#
# Note: This formula installs from source using pip and sets up the CLI.
# For the .app bundle, use the cask or DMG installer instead.

class Speaktype < Formula
  desc "AI-powered voice input method for macOS with push-to-talk dictation"
  homepage "https://github.com/Konoyo-014/SpeakType"
  url "https://github.com/Konoyo-014/SpeakType.git", tag: "v2.1.3"
  version "2.1.3"
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
        - Input Monitoring (for the global hotkey)

      Grant these in: System Settings > Privacy & Security

      For AI text polishing, install and run Ollama:
        brew install ollama
        brew services start ollama
        ollama pull huihui_ai/qwen3.5-abliterated:9b-Claude

      Start SpeakType:
        speaktype
    EOS
  end

  test do
    assert_predicate libexec / "main.py", :exist?
    assert_predicate libexec / "speaktype" / "__init__.py", :exist?
  end
end

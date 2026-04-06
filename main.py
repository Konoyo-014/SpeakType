#!/usr/bin/env python3
"""SpeakType - AI Voice Input Method for Mac

Usage:
    python main.py          # Run the menubar app
    python main.py --test   # Quick test of ASR + LLM
"""

import sys
from pathlib import Path


def _prefer_unzipped_bundle_packages():
    """Prefer filesystem packages over python310.zip inside bundled apps."""
    resources_dir = Path(__file__).resolve().parent
    bundle_lib = resources_dir / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    if not bundle_lib.exists():
        return
    bundle_lib_str = str(bundle_lib)
    if bundle_lib_str in sys.path:
        sys.path.remove(bundle_lib_str)
    sys.path.insert(0, bundle_lib_str)


_prefer_unzipped_bundle_packages()

def main():
    if "--test" in sys.argv:
        raise SystemExit(test_pipeline())
    else:
        from speaktype.app import run
        run()


def test_pipeline():
    """Quick test of the ASR and LLM pipeline."""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    print("=== SpeakType Pipeline Test ===\n")

    # Test 1: Check Ollama
    print("1. Checking Ollama...")
    from speaktype.polish import PolishEngine
    polish = PolishEngine()
    if polish.check_available():
        print("   ✓ Ollama is running and model is available")
    else:
        print("   ✗ Ollama not available (text polishing will be disabled)")

    # Test 2: Load ASR
    print("\n2. Loading ASR model...")
    from speaktype.asr import ASREngine
    asr = ASREngine()
    try:
        asr.load()
        print("   ✓ ASR model loaded")
    except Exception as e:
        print(f"   ✗ ASR load failed: {e}")
        print("\n=== Test Failed ===")
        return 1

    # Test 3: Record and transcribe
    print("\n3. Recording test (speak for 3 seconds)...")
    from speaktype.audio import AudioRecorder
    import time

    recorder = AudioRecorder()
    recorder.start()
    for i in range(3, 0, -1):
        print(f"   Recording... {i}s")
        time.sleep(1)
    audio_path = recorder.stop()

    if audio_path:
        print("   Transcribing...")
        text = asr.transcribe(audio_path)
        print(f"   Raw: {text}")
        if not text.strip():
            print("   ✗ Empty transcription (check microphone permissions, input level, and ambient noise)")
            print("\n=== Test Failed ===")
            return 1

        if polish._available:
            print("   Polishing...")
            polished = polish.polish(text)
            print(f"   Polished: {polished}")
            if not polished.strip():
                print("   ✗ Empty polished output (check the Ollama model)")
                print("\n=== Test Failed ===")
                return 1
    else:
        print("   ✗ No audio captured (mic issue?)")
        print("\n=== Test Failed ===")
        return 1

    print("\n=== Test Complete ===")
    return 0


if __name__ == "__main__":
    main()

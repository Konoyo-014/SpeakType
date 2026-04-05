#!/usr/bin/env python3
"""SpeakType - AI Voice Input Method for Mac

Usage:
    python main.py          # Run the menubar app
    python main.py --test   # Quick test of ASR + LLM
"""

import sys

def main():
    if "--test" in sys.argv:
        test_pipeline()
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
        return

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

        if polish._available:
            print("   Polishing...")
            polished = polish.polish(text)
            print(f"   Polished: {polished}")
    else:
        print("   ✗ No audio captured (mic issue?)")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    main()

import argparse
from multiprocessing.connection import Connection
import os
from pathlib import Path
import queue
import sys
import threading
import time

script_directory = Path(__file__).resolve().parent
if script_directory.name == "Resources" and script_directory.parent.name == "Contents":
    sys.path.insert(0, str(script_directory / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"))
else:
    sys.path.insert(0, str(script_directory.parent))
sys.dont_write_bytecode = True

from speaktype.sounddevice_compat import prepare_sounddevice_import

prepare_sounddevice_import()
import sounddevice as sd


def capture(connection):
    configuration = connection.recv()
    sample_rate = configuration["sample_rate"]
    device = configuration["device"]
    maximum_seconds = configuration["max_seconds"]
    events = queue.Queue()
    parent_pid = os.getppid()
    parent_watch_stop = threading.Event()

    def watch_parent():
        while not parent_watch_stop.wait(0.2):
            if os.getppid() != parent_pid:
                os._exit(1)

    threading.Thread(target=watch_parent, daemon=True, name="SpeakTypeMicrophoneParentWatch").start()

    def audio_callback(indata, frames, time_info, status):
        if status:
            events.put(("error", RuntimeError(f"Microphone input failed: {status}")))
            raise sd.CallbackAbort
        events.put(("audio", indata.copy()))

    connection.send(("opening", dict(sd.query_devices(device, kind="input"))))
    stream = sd.InputStream(device=device, samplerate=sample_rate, channels=1, dtype="float32",
                            callback=audio_callback, blocksize=int(sample_rate * 0.1))
    try:
        stream.start()
        started = time.monotonic()
        ready_sent = False
        stopping = False
        while not stopping:
            if connection.poll(0.01):
                command, payload = connection.recv()
                if command != "stop":
                    raise ValueError(f"Unknown microphone command: {command}")
                stopping = True
            if maximum_seconds is not None and time.monotonic() - started >= maximum_seconds:
                connection.send(("limit", None))
                stopping = True
            while not events.empty():
                event = events.get_nowait()
                if event[0] == "audio" and not ready_sent:
                    connection.send(("ready", None))
                    ready_sent = True
                if event[0] == "error":
                    raise event[1]
                connection.send(event)
        stream.stop()
        while not events.empty():
            connection.send(events.get_nowait())
        connection.send(("stopped", None))
    finally:
        stream.close()
        parent_watch_stop.set()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--connection-fd", type=int, required=True)
    args = parser.parse_args()
    connection = Connection(args.connection_fd)
    try:
        capture(connection)
    except Exception as error:
        connection.send(("error", error))
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()

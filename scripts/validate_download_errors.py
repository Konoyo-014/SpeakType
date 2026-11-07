import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading

import httpx2


repository = Path(__file__).resolve().parents[1]
bundle = Path(os.environ["SPEAKTYPE_TEST_BUNDLE"]).resolve() if os.environ.get("SPEAKTYPE_TEST_BUNDLE") else None
sys.path.insert(0, str(bundle / "Contents/Resources/lib/python3.10") if bundle else str(repository))

from speaktype.model_download import download_error_message


parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path, default=repository / "work/download-errors-report.json")
args = parser.parse_args()
(repository / "work").mkdir(exist_ok=True)
report = {"runtime": str(bundle) if bundle else "source", "cases": []}


def check_failure(name, operation, expected):
    try:
        operation()
    except (httpx2.HTTPError, OSError) as error:
        message = download_error_message(error)
        assert expected in message, message
        assert "详细原因：" in message and (str(error).strip() or type(error).__name__) in message, message
        report["cases"].append({"name": name, "exception": type(error).__name__, "message": message})
    else:
        raise AssertionError(f"Expected an actual network failure: {name}")


def request_status(url, method="GET"):
    response = httpx2.request(method, url, timeout=2, trust_env=False)
    response.raise_for_status()


with tempfile.TemporaryDirectory(dir=repository / "work", prefix="download-errors-") as temporary:
    work = Path(temporary)
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        closed_port = reserved.getsockname()[1]
    check_failure("closed_connection", lambda: request_status(f"http://127.0.0.1:{closed_port}/"), "无法连接模型下载服务")
    check_failure("dns_resolution", lambda: request_status("http://speaktype-network-check.invalid/"), "无法解析")

    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen(1)
        silent_port = silent.getsockname()[1]
        check_failure("read_timeout", lambda: httpx2.get(f"http://127.0.0.1:{silent_port}/", timeout=0.15, trust_env=False),
                      "等待模型下载数据超时")

    handler = partial(SimpleHTTPRequestHandler, directory=str(work))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/unavailable-model"
        check_failure("missing_file_http_404", lambda: request_status(url), "HTTP 404")
        check_failure("unsupported_method_http_501", lambda: request_status(url, "POST"), "HTTP 501")

        environment = dict(os.environ, HF_ENDPOINT=f"http://127.0.0.1:{server.server_port}",
                           HF_HOME=str(work / "huggingface"), HF_HUB_CACHE=str(work / "huggingface/hub"),
                           HF_HUB_DISABLE_IMPLICIT_TOKEN="1", SPEAKTYPE_MODEL_DOWNLOAD_WORKER="1",
                           TMPDIR=str(work), NO_PROXY="127.0.0.1", no_proxy="127.0.0.1")
        command = ([str(bundle / "Contents/MacOS/model_download_worker")] if bundle else
                   [sys.executable, str(repository / "speaktype/model_download_worker.py")])
        result = subprocess.run([*command, "--model", "unavailable/model"], env=environment,
                                text=True, encoding="utf-8", capture_output=True, timeout=20)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        assert result.returncode != 0, result
        assert events[-1]["state"] == "error" and "HTTP 404" in events[-1]["message"], events
        assert "Dry run cannot" not in events[-1]["message"], events
        assert "Traceback" in result.stderr, result.stderr
        report["cases"].append({"name": "worker_exits_on_real_http_failure", "returncode": result.returncode,
                                "events": events, "traceback_preserved": True})
    finally:
        server.shutdown()
        server.server_close()
        serving.join(timeout=2)

    certificate = work / "certificate.pem"
    private_key = work / "private-key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-subj", "/CN=localhost", "-keyout", str(private_key), "-out", str(certificate)],
                   check=True, capture_output=True)
    secure_server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, private_key)
    secure_server.socket = context.wrap_socket(secure_server.socket, server_side=True)
    serving = threading.Thread(target=secure_server.serve_forever, daemon=True)
    serving.start()
    try:
        check_failure("untrusted_certificate", lambda: request_status(f"https://127.0.0.1:{secure_server.server_port}/"),
                      "无法验证模型下载服务的安全证书")
    finally:
        secure_server.shutdown()
        secure_server.server_close()
        serving.join(timeout=2)

args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(report, indent=2, ensure_ascii=False))
print(f"REPORT {args.report}")

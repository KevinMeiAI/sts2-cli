from __future__ import annotations
import json
import queue
import subprocess
import threading
from pathlib import Path
from .common import minimal_env


class EngineError(RuntimeError):
    pass


class Engine:
    def __init__(self, root, stderr_path, timeout=30):
        self.timeout = timeout
        self.replies = queue.Queue()
        self.faults = []
        self.error_file = open(stderr_path, 'w')
        root = Path(root).resolve()
        self.proc = subprocess.Popen([str(root / 'sts2'), 'json'], cwd=root,
            env=minimal_env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1)
        self.read_thread = threading.Thread(target=self._read, daemon=True)
        self.err_thread = threading.Thread(target=self._stderr, daemon=True)
        self.read_thread.start()
        self.err_thread.start()
        try:
            ready = self.receive()
            if ready.get('type') != 'ready':
                raise EngineError('Engine did not become ready')
        except Exception:
            self.close()
            raise

    def _read(self):
        try:
            for line in self.proc.stdout:
                if line.startswith('{'):
                    self.replies.put(json.loads(line))
        except Exception as error:
            self.replies.put(EngineError(type(error).__name__))
        finally:
            self.replies.put(EngineError('Game process closed stdout'))

    def _stderr(self):
        for line in self.proc.stderr:
            self.error_file.write(line)
            self.error_file.flush()
            if '[ERROR]' in line or 'Exception' in line or 'timeout' in line.lower():
                self.faults.append(line.rstrip())

    def receive(self):
        try:
            result = self.replies.get(timeout=self.timeout)
        except queue.Empty:
            raise EngineError('Game command timed out') from None
        if isinstance(result, Exception):
            raise result
        return result

    def send(self, command):
        try:
            self.proc.stdin.write(json.dumps(command) + '\n')
            self.proc.stdin.flush()
        except (OSError, ValueError):
            raise EngineError('Cannot send a command to the closed game process') from None
        return self.receive()

    def close(self):
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write('{"cmd":"quit"}\n')
                self.proc.stdin.flush()
                self.proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                self.proc.kill()
                self.proc.wait(timeout=3)
        self.read_thread.join(timeout=1)
        self.err_thread.join(timeout=1)
        self.error_file.close()
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            stream.close()

"""Bound per-process login abuse state; deployment/IdP policies remain explicit gates."""
import threading
import time
from collections import OrderedDict


class LoginLimit:
    def __init__(self, *, clock=time.monotonic, per_peer=60, total=300, window_s=60, peers=1024):
        self.clock, self.per_peer, self.total, self.window_s, self.peers = clock, per_peer, total, window_s, peers
        self.entries, self.global_times, self.lock = OrderedDict(), [], threading.Lock()

    def allowed(self, peer):
        with self.lock:
            now = self.clock()
            self.global_times = [stamp for stamp in self.global_times if stamp > now-self.window_s]
            if len(self.global_times) >= self.total:
                return False
            stamps = [stamp for stamp in self.entries.get(peer, []) if stamp > now-self.window_s]
            if len(stamps) >= self.per_peer:
                return False
            self.global_times.append(now)
            self.entries[peer] = [*stamps, now]
            self.entries.move_to_end(peer)
            while len(self.entries) > self.peers:
                self.entries.popitem(last=False)
            return True

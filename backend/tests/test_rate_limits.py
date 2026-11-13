from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app import main
class FakeRedis:
    def __init__(self): self.values, self.sets = {}, {}
    def incr(self, key): self.values[key] = int(self.values.get(key, 0)) + 1; return self.values[key]
    def expire(self, key, seconds): pass
    def ttl(self, key): return 60
    def eval(self, script, keys, owner, stream):
        members = self.sets.setdefault(owner, set())
        if len(members) >= 2: return 0
        members.add(stream); return 1
def test_rate_limit_and_atomic_slot_reservation(monkeypatch):
    redis = FakeRedis(); monkeypatch.setattr(main, "redis_client", lambda: redis)
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="198.51.100.2")); owner = main._consume_record_quota(request)
    assert main._reserve_recording_slot(owner, "one") and main._reserve_recording_slot(owner, "two") and not main._reserve_recording_slot(owner, "three")
    main._consume_record_quota(request)
    with pytest.raises(HTTPException) as error: main._consume_record_quota(request)
    assert error.value.status_code == 429

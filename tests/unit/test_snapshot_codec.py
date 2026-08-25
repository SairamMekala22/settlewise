from recon.application.service import ReconciliationApplication
from recon.persistence.codec import decode_snapshot, encode_snapshot


def test_run_snapshot_json_codec_round_trips_exact_financial_state() -> None:
    original = ReconciliationApplication().create_demo_run(seed=441, order_count=200)
    decoded = decode_snapshot(encode_snapshot(original))
    assert decoded == original

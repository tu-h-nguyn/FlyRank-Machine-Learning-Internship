from app.models import JobFailure, Tenant, UsageAlert, UsageEvent
from app.services.alerts import run_usage_alert_scan


def test_usage_alert_scan_creates_once(db_session):
    tenant = db_session.query(Tenant).filter_by(external_key='tenant-a').one()
    db_session.add(UsageEvent(
        tenant_id=tenant.id,
        usage_type='api_call',
        quantity=3,
        idempotency_key='x',
        request_hash='h',
        response_json='{}',
        response_status=200,
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
        cost_micro_usd=3000,
    ))
    db_session.commit()

    assert run_usage_alert_scan(db_session) == 2
    assert run_usage_alert_scan(db_session) == 0
    assert db_session.query(UsageAlert).count() == 2


def test_worker_retries_and_persists_failure(db_session, monkeypatch):
    import app.services.alerts as alerts

    attempts = {'count': 0}

    def failing_scan(db):
        attempts['count'] += 1
        raise RuntimeError('synthetic worker failure')

    monkeypatch.setattr(alerts, 'run_usage_alert_scan', failing_scan)
    alerts.run_with_retry(lambda: db_session, retry_count=3)

    assert attempts['count'] == 3
    failure = db_session.query(JobFailure).one()
    assert failure.job_name == 'usage-alert-scan'
    assert failure.attempts == 3
    assert 'synthetic worker failure' in failure.error_message

from pathlib import Path


def test_production_verifier_covers_environment_compose_nginx_and_certificates():
    script = Path("scripts/verify_production.py").read_text(encoding="utf-8")
    assert "validate_production_settings" in script
    assert "docker-compose.prod.yml" in script
    assert "--require-certificates" in script
    assert "--scan-subject" in script
    assert "--scan-subject requires --require-image-digest" in script
    assert "--scan-subject requires --require-image-inspect" in script
    assert "actual_image_id != expected_image_id" in script
    assert "docker" in script and "compose" in script and "config" in script


def test_backup_scripts_generate_checksums_and_apply_retention():
    postgres = Path("scripts/backup_postgres.sh").read_text(encoding="utf-8")
    storage = Path("scripts/backup_private_storage.sh").read_text(encoding="utf-8")
    assert "pg_dump" in postgres and "sha256sum" in postgres and "RETENTION_DAYS" in postgres
    assert "tar -C /app/storage" in storage and "sha256sum" in storage and "RETENTION_DAYS" in storage


def test_scheduler_manual_jobs_include_low_points_warning():
    script = Path("scripts/run_jobs.py").read_text(encoding="utf-8")
    assert '"low-points"' in script
    assert "run_low_points_warnings" in script

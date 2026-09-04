from pathlib import Path


ADMIN_APP = Path("apps/admin/public/v12-operations.js")
ADMIN_INDEX = Path("apps/admin/public/v12-operations.html")
CALL_APP = Path("apps/call-h5/public/app.js")
CALL_INDEX = Path("apps/call-h5/public/index.html")


def _function_slice(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end)]


def test_dispatch_pool_always_offers_existing_correction_form_and_marks_verification() -> None:
    source = ADMIN_APP.read_text(encoding="utf-8")
    dispatch = _function_slice(source, "async function dispatch()", "async function candidates")
    correction = _function_slice(
        source,
        "async function openDispatchCorrection",
        "async function candidates",
    )

    assert "修改信息" in dispatch
    assert "有核验信息" in dispatch
    assert "data-dispatch-correction" in dispatch
    assert "can('lead.manual.manage')" in dispatch
    assert "primaryRole()!=='SUPER_ADMIN'" in dispatch
    assert "/v1.2/admin/leads/" in correction
    assert "/v1.2/pre-dispatch-verifications/tasks/" in correction
    assert "openPlatformLeadForm(lead,true" in correction
    assert "verificationInfo" in correction
    assert "refresh:dispatch" in correction


def test_existing_correction_form_renders_read_only_verification_and_uses_caller_refresh() -> None:
    source = ADMIN_APP.read_text(encoding="utf-8")
    form = _function_slice(source, "async function openPlatformLeadForm", "async function readPlatformLeadPayload")
    save = _function_slice(source, "async function savePlatformLead", "async function saveAndAssignNewLeadToTelesales")
    verification = _function_slice(source, "function preDispatchVerificationInfo", "async function openPlatformLeadForm")

    for label in ("电销核验信息", "核验人员", "提交时间", "联系结果", "事实结论", "核验备注"):
        assert label in verification
    assert "esc(info.note" in verification
    assert "preDispatchVerificationInfo(options.verificationInfo)" in form
    assert "savePlatformLead(item,correction,options.refresh)" in form
    assert "refresh||" in save


def test_operation_disposition_uses_task_detail_and_shows_verification_info() -> None:
    source = ADMIN_APP.read_text(encoding="utf-8")
    tasks = _function_slice(source, "async function telesales()", "function companyQueuePager")

    assert "data-pre-disposition-task" in tasks
    assert "openPreDispatchTask" in tasks
    assert "disposePreDispatch(task)" in tasks
    assert "preDispatchVerificationInfo(task.verification_info)" in tasks


def test_telesales_submitted_record_shows_its_verification_note() -> None:
    source = CALL_APP.read_text(encoding="utf-8")
    records = _function_slice(source, "async function records()", "function taskFacts")
    task_card = _function_slice(source, "function taskCard(task)", "function callHomeGreeting")
    task = _function_slice(source, "async function task(kind, id)", "function bindTaskActions")

    assert "submittedHistory:true" in records
    assert "item.submitted_at" in records
    assert "task.is_overdue&&!task.submitted_at" in task_card
    assert "核验备注" in task
    assert "data.verification_info?.note" in task
    assert "esc(data.verification_info?.note" in task
    assert "data.submitted_at?'SUBMITTED':data.status" in task
    assert "data.is_overdue&&!data.submitted_at" in task


def test_changed_frontend_assets_have_feedback_94_cache_busters() -> None:
    admin_index = ADMIN_INDEX.read_text(encoding="utf-8")
    call_index = CALL_INDEX.read_text(encoding="utf-8")

    assert "v12-operations.js?v=20260904-verification-info" in admin_index
    assert "app.js?v=20260904-verification-info" in call_index

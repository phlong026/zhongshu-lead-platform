from pathlib import Path


H5 = Path("apps/h5/public")
ADMIN = Path("apps/admin/public")
RETIRED_H5_SOURCES = {
    "app.js",
    "design-system-v13.js",
    "enhancements.css",
    "enhancements.js",
    "followup-v13.css",
    "followup-v13.js",
    "index.html",
    "lead-detail-v13.css",
    "lead-detail-v13.js",
    "lead-list-v13.css",
    "lead-list-v13.js",
    "manifest.webmanifest",
    "notifications-v13.css",
    "notifications-v13.js",
    "points-enhancements.css",
    "points-enhancements.js",
    "points-v13.css",
    "points-v13.js",
    "profile-v13.css",
    "profile-v13.js",
    "return-v13.css",
    "return-v13.js",
    "status-pages-v13.css",
    "status-pages-v13.js",
    "styles.css",
    "supplier.css",
    "supplier.html",
    "supplier.js",
    "v12-supplier-entry.js",
    "v12-workbench-entry.js",
}
RETIRED_ADMIN_SOURCES = {
    "admin-design-system-v10.css",
    "admin-design-system-v10.js",
    "admin-extended-pages-v10.js",
    "api.js",
    "app.js",
    "index.html",
    "points-enhancements.css",
    "points-enhancements.js",
    "report-enhancements.css",
    "report-enhancements.js",
    "styles.css",
    "ui.js",
    "v12-entry-link.js",
    "vendor/QR-LICENSE.txt",
    "vendor/qrcode.min.js",
}


def test_retired_franchise_h5_sources_are_physically_absent() -> None:
    retained = {path.name for path in H5.iterdir() if path.is_file()}

    assert not RETIRED_H5_SOURCES.intersection(retained)
    assert {
        "design-system-v13.css",
        "logo.png",
        "safe-html.js",
        "svg-icon-system.css",
        "svg-icon-system.js",
        "v12-workbench.css",
        "v12-workbench.html",
        "v12-workbench.js",
    }.issubset(retained)


def test_retired_platform_sources_are_physically_absent() -> None:
    retained = {
        path.relative_to(ADMIN).as_posix()
        for path in ADMIN.rglob("*")
        if path.is_file()
    }

    assert not RETIRED_ADMIN_SOURCES.intersection(retained)
    assert {"logo.png", "v12-operations.css", "v12-operations.html", "v12-operations.js"}.issubset(retained)


def test_unified_franchise_workbench_does_not_load_retired_assets() -> None:
    source = (H5 / "v12-workbench.html").read_text(encoding="utf-8")

    for retired in RETIRED_H5_SOURCES:
        assert retired not in source

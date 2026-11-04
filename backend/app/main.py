import base64
import logging
import os
from contextlib import asynccontextmanager

# Force AI Studio (Gemini API) backend instead of Vertex AI for ADK.
# Vertex AI's function-calling schema rejects auto-generated fields like
# "additional_properties". MUST be set before any google.adk import.
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.security import get_current_principal, require_admin, require_roles
from app.database import init_db, run_migrations, async_session
from app.routers import invoices, products
from app.routers.invoices import start_matching_queue, stop_matching_queue
from app.routers import auth, admin, inbox, purchase_orders, po_matching, fbr, sap
from app.routers import workflows as workflows_router
from app.routers import approvals as approvals_router
from app.routers import audit as audit_router
from app.routers.internal_auth import auth_router as internal_auth_router, admin_users_router
from app.routers import gl_accounts as gl_accounts_router
from app.routers import comments as comments_router
from app.routers import notifications as notifications_router
from app.routers import role_permissions as role_permissions_router
from app.routers import currency as currency_router
from app.routers import analytics as analytics_router
from app.routers import tax_rules as tax_rules_router
from app.routers import attachments as attachments_router
from app.routers import agent_invoices as agent_invoices_router
from app.routers import po_flip as po_flip_router
from app.routers import reports as reports_router
from app.routers import app_settings as app_settings_router
from app.models.product import Product  # noqa: F401 - ensure Product table is created

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Set Google Cloud credentials — support both file path (local) and base64 JSON (cloud)
    if settings.GCP_CREDENTIALS_JSON:
        creds_path = "/tmp/service-account-key.json"
        with open(creds_path, "w") as f:
            f.write(base64.b64decode(settings.GCP_CREDENTIALS_JSON).decode("utf-8"))
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
    else:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_APPLICATION_CREDENTIALS
    await init_db()
    await run_migrations()

    # Seed products if table is empty
    from app.services.seed_products import seed_products
    async with async_session() as db:
        count = await seed_products(db)
        logger.info(f"Products in database: {count}")

    # Seed default admin user if internal_users table is empty.
    # Credentials come from env (INITIAL_ADMIN_EMAIL / INITIAL_ADMIN_PASSWORD).
    # If no password is provided, a random one is generated and logged ONCE so a
    # weak default ("admin123") is never baked into a fresh deployment.
    from app.models.internal_user import InternalUser
    from sqlalchemy import select, func
    async with async_session() as db:
        count_result = await db.execute(select(func.count(InternalUser.id)))
        if count_result.scalar() == 0:
            import secrets as _secrets
            from app.services.passwords import hash_password
            admin_email = settings.INITIAL_ADMIN_EMAIL
            admin_password = settings.INITIAL_ADMIN_PASSWORD or _secrets.token_urlsafe(16)
            generated = not settings.INITIAL_ADMIN_PASSWORD
            pw_hash = hash_password(admin_password)
            admin_user = InternalUser(
                email=admin_email,
                display_name="System Admin",
                password_hash=pw_hash,
                role="admin",
                department="IT",
                is_active=1,
            )
            db.add(admin_user)
            await db.commit()
            if generated:
                if settings.DEBUG:
                    # Local dev convenience only — never log credentials in prod.
                    logger.warning(
                        "Seeded default admin %s with a RANDOM password: %s — "
                        "log in and change it now, then set INITIAL_ADMIN_PASSWORD.",
                        admin_email, admin_password,
                    )
                else:
                    logger.warning(
                        "Seeded default admin %s with an unrecoverable random password. "
                        "Set INITIAL_ADMIN_PASSWORD and redeploy (the seed only runs on an "
                        "empty internal_users table, so reset the row or the password hash).",
                        admin_email,
                    )
            else:
                logger.info("Seeded default admin user: %s", admin_email)

    # Seed default workflow template if none exist
    from app.models.workflow import WorkflowTemplate, WorkflowStep
    async with async_session() as db:
        count_result = await db.execute(select(func.count(WorkflowTemplate.id)))
        if count_result.scalar() == 0:
            template = WorkflowTemplate(
                name="General Invoice Approval",
                description="Default two-level approval for all invoices",
                invoice_type="all",
                min_amount=0,
                max_amount=None,
                currency=None,  # NULL = matches any currency (truly "general")
                is_active=1,
                priority=100,
            )
            db.add(template)
            await db.flush()
            db.add(WorkflowStep(
                template_id=template.id, step_order=1,
                step_name="AP Manager Review",
                approver_role="ap_manager", sla_hours=24, is_required=1,
            ))
            db.add(WorkflowStep(
                template_id=template.id, step_order=2,
                step_name="Finance Director Approval",
                approver_role="finance_director", sla_hours=48, is_required=1,
            ))
            await db.commit()
            logger.info("Seeded default workflow template: General Invoice Approval (2 steps)")

    # Seed default GL accounts if none exist
    from app.models.gl_account import GLAccount
    async with async_session() as db:
        count_result = await db.execute(select(func.count(GLAccount.id)))
        if count_result.scalar() == 0:
            gl_accounts = [
                GLAccount(code="4100", name="Cost of Goods Sold", category="Expense"),
                GLAccount(code="4200", name="Professional Services", category="Expense"),
                GLAccount(code="4300", name="Utilities & Maintenance", category="Expense"),
                GLAccount(code="4400", name="Office Supplies", category="Expense"),
                GLAccount(code="4500", name="Travel & Entertainment", category="Expense"),
                GLAccount(code="4600", name="IT & Software", category="Expense"),
                GLAccount(code="4700", name="Drilling & Operations", category="Expense"),
                GLAccount(code="4800", name="Exploration Costs", category="Expense"),
                GLAccount(code="2100", name="Accounts Payable", category="Liability"),
                GLAccount(code="2200", name="Accrued Liabilities", category="Liability"),
                GLAccount(code="2300", name="Tax Payable — GST", category="Liability"),
                GLAccount(code="2400", name="Tax Payable — WHT", category="Liability"),
                GLAccount(code="1100", name="Cash & Equivalents", category="Asset"),
                GLAccount(code="1200", name="Inventory", category="Asset"),
                GLAccount(code="3100", name="Revenue — Oil & Gas", category="Revenue"),
            ]
            for acc in gl_accounts:
                db.add(acc)
            await db.commit()
            logger.info(f"Seeded {len(gl_accounts)} default GL accounts")

    # Seed default tax rules if empty
    async with async_session() as db:
        from app.models.tax_rule import TaxRule
        count_result = await db.execute(select(func.count(TaxRule.id)))
        if count_result.scalar() == 0:
            tax_rules = [
                TaxRule(rule_code="GST-STD", rule_name="Standard GST", tax_type="gst", rate=18.0,
                        applies_to="all", fbr_section="Sales Tax Act 1990", description="Standard GST rate on goods and services"),
                TaxRule(rule_code="GST-REDUCED", rule_name="Reduced GST", tax_type="gst", rate=10.0,
                        applies_to="goods", fbr_section="5th Schedule", description="Reduced rate for specified goods"),
                TaxRule(rule_code="GST-ZERO", rule_name="Zero-Rated GST", tax_type="gst", rate=0.0,
                        applies_to="goods", fbr_section="5th Schedule", description="Zero-rated exports and specified goods"),
                TaxRule(rule_code="WHT-153-GOODS", rule_name="WHT on Goods (Registered)", tax_type="wht", rate=4.5,
                        applies_to="goods", supplier_type="registered", fbr_section="Section 153(1)(a)"),
                TaxRule(rule_code="WHT-153-GOODS-U", rule_name="WHT on Goods (Unregistered)", tax_type="wht", rate=9.0,
                        applies_to="goods", supplier_type="unregistered", fbr_section="Section 153(1)(a)"),
                TaxRule(rule_code="WHT-153-SVC", rule_name="WHT on Services (Registered)", tax_type="wht", rate=8.0,
                        applies_to="services", supplier_type="registered", fbr_section="Section 153(1)(b)"),
                TaxRule(rule_code="WHT-153-SVC-U", rule_name="WHT on Services (Unregistered)", tax_type="wht", rate=16.0,
                        applies_to="services", supplier_type="unregistered", fbr_section="Section 153(1)(b)"),
                TaxRule(rule_code="WHT-PETROL", rule_name="WHT on Petroleum Products", tax_type="wht", rate=12.0,
                        applies_to="goods", sector="oil_gas", fbr_section="Section 156A"),
                TaxRule(rule_code="SED-OIL", rule_name="Special Excise Duty on Oil", tax_type="sed", rate=2.0,
                        applies_to="goods", sector="oil_gas", fbr_section="Federal Excise Act 2005"),
                TaxRule(rule_code="FED-TELECOM", rule_name="FED on Telecom", tax_type="fed", rate=19.5,
                        applies_to="services", sector="telecom", fbr_section="Federal Excise Act 2005"),
            ]
            for rule in tax_rules:
                db.add(rule)
            await db.commit()
            logger.info(f"Seeded {len(tax_rules)} default tax rules")

    # Start the serial product-matching queue worker
    await start_matching_queue()

    yield

    # Graceful shutdown: stop the worker
    await stop_matching_queue()


app = FastAPI(
    title="Invoice Management API",
    version="1.0.0",
    lifespan=lifespan,
    # Interactive API docs expose the full schema — dev only.
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # Also allow any localhost port so local dev frontends work without having
    # to enumerate every port — Vite (5173), Expo web (8081/19006), mobile web
    # preview, etc. Safe because that's only the developer's own machine, and we
    # send no credentials/cookies. Cloud origins still come from the allowlist.
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── Route protection ─────────────────────────────────────────────────────────
# Dependencies attached at include time gate EVERY route in the router:
#   auth_dep  — any authenticated principal (internal user OR supplier)
#   admin_dep — internal user with role == "admin"
# Public routers (login / OTP / signup) carry no dependency.
auth_dep = [Depends(get_current_principal)]
admin_dep = [Depends(require_admin)]

# Public — authentication entry points (must be reachable unauthenticated)
app.include_router(auth.router)                         # supplier OTP / signup / login
app.include_router(internal_auth_router)                # internal login / me / logout

# Admin-only
app.include_router(admin.router, dependencies=admin_dep)            # supplier admin
app.include_router(admin_users_router, dependencies=admin_dep)      # internal user admin
app.include_router(inbox.router, dependencies=admin_dep)            # email inbox admin
app.include_router(app_settings_router.router, dependencies=admin_dep)  # runtime settings (supplier demo OTP)

# Authenticated business endpoints (internal users or suppliers)
app.include_router(invoices.router, dependencies=auth_dep)
app.include_router(products.router, dependencies=auth_dep)
app.include_router(purchase_orders.router, dependencies=auth_dep)
app.include_router(po_matching.router, dependencies=auth_dep)
app.include_router(fbr.router, dependencies=auth_dep)
app.include_router(audit_router.router, dependencies=auth_dep)
app.include_router(workflows_router.router, dependencies=auth_dep)
app.include_router(approvals_router.router, dependencies=auth_dep)
app.include_router(gl_accounts_router.router, dependencies=auth_dep)
app.include_router(comments_router.router, dependencies=auth_dep)
app.include_router(notifications_router.router, dependencies=auth_dep)
app.include_router(role_permissions_router.router, dependencies=auth_dep)  # PUT is admin-only via route dep
app.include_router(role_permissions_router.roles_router, dependencies=auth_dep)  # mutations admin-only via route dep
app.include_router(currency_router.router, dependencies=auth_dep)
app.include_router(analytics_router.router, dependencies=auth_dep)
app.include_router(tax_rules_router.router, dependencies=auth_dep)
app.include_router(attachments_router.router, dependencies=auth_dep)
app.include_router(sap.router, dependencies=auth_dep)
app.include_router(agent_invoices_router.router, dependencies=auth_dep)
app.include_router(po_flip_router.router, dependencies=auth_dep)
# Reports — restricted to admin + purchasers (ap_operator) (gated at include-time).
app.include_router(reports_router.router, dependencies=[Depends(require_roles("admin", "ap_operator"))])


@app.get("/health")
async def health():
    return {"status": "ok"}

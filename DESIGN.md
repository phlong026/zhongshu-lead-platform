# Design

## Source of truth

- Status: Active.
- Last refreshed: 2026-08-26.
- Primary product surfaces: platform operations desktop (`/admin/`), platform mobile workbench (`/h5/admin/`), franchise workbench (`/h5/`), and telesales console (`/h5/call/`).
- Evidence reviewed:
  - `apps/admin/public/v12-operations.js` and `v12-operations.css`
  - `apps/admin/public/v12-operations.js`（已承接原独立客资页）
  - `apps/h5/public/v12-workbench.js`
  - `apps/api/src/services/rbac.py`
  - `apps/api/src/core/v12_enums.py`
  - `apps/api/src/routers/v12_lead_supply.py`, `v12_returns.py`, `v12_insights.py`

## Brand

- Personality: professional, dependable, calm, operationally clear.
- Trust signals: masked personal data by default, explicit status and owner, visible deadlines, irreversible-operation confirmations, traceability link on every business detail.
- Avoid: role-mixed dashboards, unexplained technical status codes, hidden state changes, finance actions in operational workspaces, and links that open the legacy shell.

## Product goals

- Goals:
  - One role has one clear workbench, one primary action, and only the data it needs.
  - A lead can be traced from source through review, dispatch, claim, follow-up, return, points, reward, and notification.
  - Telesales verifies facts; operations decides business disposition; super admin controls funds and system rules.
  - The V1.2 web shell is the sole platform-administration shell.
- Non-goals:
  - Do not reproduce the legacy administrative interface inside the new shell.
  - Do not allow role combination to decide a different home page or expose conflicting actions.
  - Do not expose full customer contact data outside the necessary task context.
- Success signals:
  - Each role completes its primary daily flow without leaving its workbench.
  - No V1.2 navigation link points to `index.html#/...` or another legacy page.
  - Every blocked item exposes its next owner, reason, deadline, and direct next action.

## Personas and jobs

| Persona | Primary job | Home-page answer |
|---|---|---|
| Super admin | Govern the system and funds safely | What system or money risk requires attention today? |
| Operations admin | Move leads and exceptions through the business flow | Which items require my decision now? |
| Telesales | Verify facts for assigned tasks | Which calls must I complete today, and what evidence is required? |
| Franchise owner | Run company intake, claims, staff requests, and exceptions | What can my company receive, supply, or resolve now? |
| Franchise employee | Complete assigned lead work | Which customer or evidence task is assigned to me next? |

## Information architecture

### Entry boundaries

- `/admin/`: super admin and operations admin desktop workbench. It always opens the V1.2 platform shell.
- `/h5/admin/` (new): super admin and operations admin mobile workbench for queue handling, approvals, exceptions and role-allowed finance actions; complex batch management remains on desktop.
- `/h5/call/`: telesales responsive console for desktop and mobile. Mobile is the primary call-handling surface.
- `/h5/`: franchise owner and franchise employee responsive company workbench. Mobile is primary; it remains usable in a desktop browser without a second franchise administration shell.
- `/call/` is retained only as a compatibility redirect to `/h5/call/`; `/m/` is not introduced.
- An account has exactly one business role. Super administrators and operations administrators remain separate accounts; a super administrator may directly create, enable, disable, or bind franchise accounts when necessary, and every such operation requires a reason and high-risk audit record.

### Shared shell rules

- Desktop left sidebar: role-relevant navigation followed by one fixed identity card. The card shows avatar, account, role and company where applicable, and is the only entry to personal account operations.
- Desktop business pages have no persistent top title/action bar. Each page owns its primary heading and actions inside the content area so there is no duplicated page title. Sign-out lives behind the identity card.
- `异常` and `日志` are secondary governance surfaces reached from the identity-card workspace, not permanent business-navigation items.
- Each list item exposes: current status, current owner, source, latest action, deadline, and a `查看全流程` entry.
- Every detail page uses one chronological timeline. The timeline combines business actions, audit actions, points events, verification conclusions, and notification delivery state.
- “Settings” is not a generic link. It is a named, permission-scoped navigation group.

### Super-admin information architecture

1. 首页（经营总览）
2. 客资总览
3. 加盟商
4. 资金
5. 身份卡片入口（安全、平台设置、异常与日志）

### Operations-admin information architecture

1. 今日待办
2. 客资中心
3. 电销核验协同
4. 派发中心
5. 加盟商审核
6. 身份卡片入口（安全、异常与日志）

### Telesales information architecture

1. 我的任务
2. 待拨打
3. 已提交
4. 任务详情
5. 我的绩效（只读）

### Franchise-owner information architecture

1. 公司首页
2. 领取与分配
3. 供资管理
4. 跟进与退回
5. 公司与人员申请
6. 积分与奖励
7. 消息与我的

### Franchise-employee information architecture

1. 我的待办
2. 我的跟进
3. 我的供资草稿
4. 我的退回补证
5. 消息与我的

## Role page contracts

### Super admin

| Page | Primary content | Primary actions | Must not distract with |
|---|---|---|---|
| 系统总览 | 高风险审计、异常通知、账户/公司停用、资金异常、积压告警 | Drill into risk, assign governance follow-up | Normal lead review queues |
| 账号与组织 | Internal accounts, franchise account lifecycle, role/status history | Create, invite, enable, disable, bind company accounts; record reasoned franchise-account actions | Customer details |
| 加盟商治理 | Company status, capability/area approval state, owner binding state | View, emergency suspend, audit | Daily dispatch actions |
| 积分与资金 | Recharge, balance exception, price rules, rewards, immutable ledger | Recharge, adjustment, reversal, publish rule | Operations-owned review controls |
| 业务规则 | Workday calendar, notification templates/configuration, master data | Configure and publish | Individual task queues |
| 审计与通知 | Unified audit search, failed notification delivery | Retry notification, export audit | Mutable business actions |

Home metrics: high-risk operations, failed notifications, frozen rewards, unreconciled points, pending account requests, disabled-company impact.

### Operations admin

| Page | Primary content | Primary actions | Exit state |
|---|---|---|---|
| 今日待办 | Counts and priority list: initial review, telesales conclusions, pending dispatch, return final review, company review, overdue items | Assign telesales, enter work item | A named item moves to its next owner/state |
| 客资中心 | Unified source-aware lead list with queue tabs | Initial review, dedup decision, send to telesales, return to supplier, close invalid, approve to pool | Lead enters verification, pool, rework, duplicate, or closed state |
| 电销核验协同 | Pre-dispatch verification and return verification are distinct tabs | Assign/reassign, view conclusion, send back for clarification | Operations decision queue or return final review |
| 派发中心 | Ready-dispatch pool, candidate eligibility, claimed/unclaimed status | Manual dispatch, release expired assignment | Assignment created or lead remains actionable |
| 加盟商审核 | Company applications; capability and service-area changes together | One-click profile approval or reject/request changes | Company receives usable status and notification |
| 异常与退回 | Return cases, evidence, telesales conclusion, deadline | Approve, reject, require more evidence | Refund/repool, restore follow-up, or evidence rework |
| 业务追溯 | Search by lead/company/assignment/task ID | View timeline, export business record | Read-only evidence |

Home metrics: pending initial review, pending telesales conclusion, pending operations disposition, ready to dispatch, pending return final review, company approval backlog, SLA overdue count.

### Telesales

| Page | Primary content | Primary actions | Guardrail |
|---|---|---|---|
| 我的任务 | Operations-assigned tasks sorted by SLA and task type | Start assigned task | Does not show unrelated leads or provide self-claim/reassignment |
| 待拨打 | Customer facts, permitted phone details, prior notes, required checklist | Record contact attempt, call result, evidence note | No dispatch, return, close, or points buttons |
| 提交结论 | Structured factual conclusion: verified qualified, information incomplete, unverifiable, invalid/duplicate evidence | Submit conclusion | Submitting sends item to operations; it never performs final disposition |
| 已提交 | Read-only past submissions and operations outcome | View outcome | Cannot rewrite final business decision |

Home metrics: due today, overdue, in progress, awaiting clarification, submitted today.

### Franchise owner

| Page | Primary content | Primary actions | Guardrail |
|---|---|---|---|
| 公司首页 | Available points, waiting claims, active follow-up, required rework, pending returns, unread messages | Go to the highest-priority company task | No platform-wide data |
| 领取与分配 | Pending claims, claimed leads, employee assignment status | Claim lead, assign/reassign employee | Claim is the only company-side action that spends points |
| 供资管理 | New supply, drafts, review feedback, rework queue | Create/submit supply, assign supplier-entry work | Cannot self-approve or put leads in pool |
| 跟进与退回 | Company lead progress, return drafts, evidence and outcomes | Review follow-up, submit return, supplement evidence | Return outcome is platform-owned |
| 公司与人员申请 | Company profile/area/capability status, employee roster and requests | Submit profile update and employee add/disable request | Cannot grant roles or see passwords |
| 积分与奖励 | Balance, reservations, ledger, reward status | Read-only and contact platform for recharge | Cannot recharge, adjust, or reverse |

Home metrics: available points, waiting to claim, active follow-up, supplier rework required, return pending, employee requests pending.

### Franchise employee

| Page | Primary content | Primary actions | Guardrail |
|---|---|---|---|
| 我的待办 | Leads and evidence tasks explicitly assigned to this employee | Open next task | No company-wide pool or financial data |
| 我的跟进 | Assigned lead details, next action, follow-up history | Add follow-up, mark success, request return | “Invalid” opens the formal return request, not a terminal shortcut |
| 我的供资草稿 | Personal drafts and items returned for correction | Edit and resubmit | Cannot approve or dispatch |
| 我的退回补证 | Cases where platform requested additional materials | Upload evidence and resubmit | Cannot final-review the return |

Home metrics: due follow-ups, uncontacted leads, rework due, return evidence due, unread messages.

### H5 bottom navigation contract

The bottom navigation is a role-specific task switcher, not a sitemap. It has at most five items. A role must never see a disabled, irrelevant, or legacy navigation item. Notifications are a badge on the current task or `我的`, rather than a standalone bottom tab; a badge appears only when the user has an actionable unread event.

| Role | Bottom navigation, in order | Why these items are primary | Important functions reached inside the pages, not as bottom tabs |
|---|---|---|---|
| 超级管理员 | 首页 · 治理 · 资金 · 我的 | Mobile use is for risk observation and emergency governance; funds remain clearly separated | Account detail, company detail, rules, audit, notification failures |
| 运营管理员 | 首页 · 客资 · 派发 · 异常 · 我的 | Mirrors the operation flow: decide, process lead, dispatch, resolve exception | Company audit is an operation queue in 首页; telesales collaboration is embedded in 客资/异常 detail |
| 电销人员 | 首页 · 核验 · 记录 · 我的 | Keeps the worker focused on the next call and fact submission | Task history, call checklist, evidence and performance summary |
| 加盟商负责人 | 首页 · 接收 · 供资 · 跟进 · 我的 | Separates company receiving, supplying, and post-claim work without putting finance in the main path | Return applications under 跟进; points, rewards, company profile, staff requests and messages under 我的 |
| 加盟商员工 | 首页 · 跟进 · 供资 · 我的 | Shows only personally assigned work and removes company-wide decisions | Return evidence is reached from the relevant task; messages and profile are under 我的 |

H5 navigation interaction rules:

- The first tab is always `首页`. Its first module is `待办`, and it becomes the default focus when a user has overdue or assigned work.
- `我的` contains identity, messages, password/help, and role-appropriate secondary settings; it is not a catch-all business menu.
- The home/queue has no more than four KPI cards. Every card must lead to a filtered actionable list.
- Return, evidence rework, company review, and telesales conclusion are deep-linked task states, not always-visible tabs.
- A user never sees another role's workflow as an empty tab. For example, franchise staff never see points, and telesales never see dispatch.
- H5 deep links must stay in the V1.2 role workbench and must never open legacy `/h5/index.html` or `/admin/index.html#/...` routes.

### Internal mobile page contracts

`/h5/admin/` is one responsive V1.2 platform-mobile shell. It renders the super-admin or operations-admin contract after the server returns the single role; it is not a second legacy administration app. `/h5/call/` remains the dedicated responsive telesales shell. `/call/` only redirects there for compatibility.

| Role and page | First-screen content | Allowed mobile actions | Deliberately desktop-only or secondary |
|---|---|---|---|
| 超级管理员 · 首页 | 待办、资金异常、失败通知、高风险操作、待处理账号/公司事项 | Open and resolve a single urgent item | Batch search, long audit exports, broad rule editing |
| 超级管理员 · 治理 | 账号/公司申请、停用风险、关键规则变更记录 | Approve or reject a single request, emergency disable | Bulk account management and role migration |
| 超级管理员 · 资金 | 待处理充值、异常余额、冻结奖励、最近资金流水 | Recharge, adjustment, reversal, publish one reviewed rule | Batch reconciliation and large ledger analysis |
| 超级管理员 · 我的 | Identity, actionable messages, help, sign-out | Read personal messages | System configuration |
| 运营管理员 · 首页 | 待初审、待电销结论、待运营处置、待派发、待终审 | Open the highest-priority item | Historical reports and batch actions |
| 运营管理员 · 客资 | Source-aware queues with one clear filter at a time | Review, send to telesales, return for correction, close, approve to pool | Bulk import/export and complex dedup investigation |
| 运营管理员 · 派发 | Ready pool, eligible candidates, expiring assignments | Confirm one manual dispatch or release | Large candidate comparison and batch dispatch |
| 运营管理员 · 异常 | Returns, overdue tasks, company-review exceptions, notification failures | Assign telesales, final-review a return, request evidence | Full audit export and rule management |
| 运营管理员 · 我的 | Identity, messages, help, sign-out | Read personal messages | Company/fund administration |
| 电销人员 · 首页 | 待办、今日到期、核验中、已提交、唯一“继续核验”按钮 | Start or resume own task | Other employees' tasks and business decisions |
| 电销人员 · 核验 | Current task, permitted phone, checklist, evidence and result form | User-tapped dial, record contact result, submit factual conclusion | Dispatch, return decision, lead closing, funds |
| 电销人员 · 记录 | Submitted personal tasks and the operations outcome | View own task history | Edit submitted conclusions |
| 电销人员 · 我的 | Identity, messages, help, sign-out | Read personal messages | Business queues |

Mobile call rule: the `拨号` button is visible only to the assigned telesales user while the task is in progress. It first records the dial action, then opens the device dialer through a validated `tel:` URL. The H5 page never initiates a silent call, starts recording, or exposes the number to operations users.

## Design principles

1. Role before module: navigation follows a person’s responsibility, not a database table.
2. Queue before report: the home page prioritizes actionable work, then summary metrics.
3. One decision, one owner: a page never offers an action owned by another role.
4. State is human-readable: status includes current owner, next step, reason, deadline, and source.
5. Traceability is adjacent: every lead/assignment/task detail has a visible full-process timeline.

Tradeoffs:

- Fewer menus and roles reduce flexibility, but prevent accidental privilege mixing and navigation ambiguity.
- Company staff receive tighter scope than owners; this is intentional to protect points and customer data.
- The operations workbench becomes denser than the franchise workbench because it is a decision center, not a reporting portal.

## Visual language

- Color: preserve the existing warm neutral surface and dark brown navigation; use semantic green/amber/red only for state and never as the sole signal.
- Typography: system Chinese sans-serif stack; 20–24px page title, 16–18px section title, 13–14px operational body text.
- Spacing/layout rhythm: 8px base scale; 24px desktop page inset; 12–16px card gaps; tables keep primary status and action columns visible.
- Shape/radius/elevation: retain rounded 10–17px cards and restrained shadows; destructive actions require clear red outline or confirmation, not visual prominence by default.
- Motion: short transition only for navigation, sheet/modal, toast, and loading; honor reduced-motion preference.
- Imagery/iconography: use existing SVG icon system; no decorative imagery that competes with operational information.

## Components

- Existing components to reuse: V1.2 sidebar shell, KPI cards, table rows, status badges, modal/sheet, toast, safe HTML helpers, SVG icons.
- New or changed components:
- Role identity card at the bottom of desktop navigation.
- Identity-card workspace: concise account identity, login security, and only the required governance tools (system settings, exceptions, audit) in one page.
- Cascading service-area picker: one control containing province and city dropdowns plus multi-select district/county checkboxes; it submits only canonical region codes.
  - `我的待办` priority queue card with SLA and next-owner metadata.
  - Source-aware lead status chip: source + state + next owner.
  - Decision panel with required reason/evidence fields and result preview.
  - Unified process timeline.
  - Company personnel request card.
  - Legacy-route guard that rejects navigation to old pages.
- Variants and states: loading skeleton, permission empty state, business empty state, data masking state, failed notification state, irreversible action confirmation, success receipt.
- Token/component ownership: extend the V1.2 CSS variables and utilities; do not introduce a second design system.

## Accessibility

- Target standard: WCAG 2.1 AA for contrast, keyboard navigation, focus visibility, labels, and error messages.
- Keyboard/focus behavior: menu, modal and sheet controls have predictable tab order; opening a modal moves focus into it and closing returns focus to its trigger.
- Contrast/readability: status uses text and icon in addition to color; customer phone masking state is explicit.
- Screen-reader semantics: tables use headers; action buttons name the affected business item; status change confirmation announces success/failure.
- Reduced motion: honor `prefers-reduced-motion` for page and modal transitions.

## Responsive behavior

- Supported surfaces: desktop-first for super admin and operations; mobile-first for franchise owner/employee; focused desktop console for telesales.
- Layout adaptations: desktop sidebar collapses to icons at tablet widths; franchise uses bottom navigation; priority queue remains above charts on all widths.
- Touch/hover differences: all hover-only affordances have visible buttons on touch screens; evidence upload and call-result forms use large touch targets.

## Interaction states

- Loading: preserve shell and show skeleton/list loading in the content area.
- Empty: explain whether there is no work, no permission, or filters yielded no result; show one role-appropriate next action.
- Error: show a readable cause and retry; never leave a successful-looking empty table after a failed request.
- Success: show a receipt with resulting status, next owner, and direct link to details.
- Disabled: explain the unmet rule, such as missing company approval, insufficient points, incomplete evidence, or pending prior review.
- Offline/slow network: preserve entered form data locally until submit confirmation where practical; prevent duplicate submit via idempotency key and disabled action.

## Content voice

- Tone: direct, operational, non-technical, and accountable.
- Terminology:
  - Use “待运营处置”, not a raw status code.
  - Use “事实核验结论”, not “审核通过/驳回” for telesales.
  - Use “退回加盟商补正” for source-data rework and “退回申请” for a receiver’s post-claim appeal.
  - Use “待派发池”, “待领取”, “跟进中”, “待补证”, and “已关闭”.
- Microcopy rules: each irreversible button names its result; require an explanatory reason when rejecting, returning, closing, adjusting points, or changing access.

## Implementation constraints

- Framework/styling system: existing static HTML/JS modules, V1.2 CSS variables, and safe HTML utility.
- Design-token constraints: preserve the current neutral/brown token family; extend existing tokens instead of hardcoding per page.
- Performance constraints: dashboard loads only role-relevant summaries; lists paginate; full timelines load on demand.
- Compatibility constraints: keep `/admin/`, `/h5/admin/`, `/h5/call/`, and `/h5/` as role-specific entry URLs; retain `/call/` only as a redirect; remove legacy shell links from new navigation.
- Test/screenshot expectations: role-based browser tests must cover menu visibility, next-action CTA, blocked action explanation, no legacy routes, keyboard modal behavior, and mobile franchise workbench.

## Open questions

- No unresolved role, terminal, or finance-approval decision remains in this design scope.
- Franchise employees may submit supply leads directly, while franchise owners may submit as well.
- Franchise owners may distribute claimed leads to employees without operations visibility or approval; the system still records an internal company audit event.
- Super-admin finance actions do not require a second-super-admin review.
- Telesales uses the responsive `/h5/call/` console on both desktop and mobile; mobile supports a user-tapped `tel:` handoff to the device dialer, not silent automatic calling.

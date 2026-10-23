import { useState, useEffect } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import tmcLogo from "../../assets/tmc-logo-dark.png";
import NotificationBell from "./NotificationBell";
import { canAccessPath } from "../../config/rolePermissions";
import { pageDocumentTitle } from "../../config/brand";
import { useRoleLabel } from "../../config/roleLabels";

// Maps a route path (exact or prefix) to a page title for the top bar.
const TITLE_RULES = [
  { test: (p) => p === "/", title: "Analytics & Insights" },
  { test: (p) => p.startsWith("/ap-visibility"), title: "AP Visibility" },
  { test: (p) => p.startsWith("/ap"), title: "Purchaser Dashboard" },
  { test: (p) => p.startsWith("/tax-rules"), title: "FBR Tax Rules" },
  { test: (p) => p.startsWith("/tax"), title: "Tax Manager Dashboard" },
  { test: (p) => p.startsWith("/auditor"), title: "Auditor Dashboard" },
  { test: (p) => p.startsWith("/approvals"), title: "My Approvals" },
  { test: (p) => p.startsWith("/upload"), title: "Upload Invoice" },
  { test: (p) => p.startsWith("/results"), title: "Extraction Results" },
  { test: (p) => p.startsWith("/invoices/"), title: "Invoice Detail" },
  { test: (p) => p.startsWith("/invoices"), title: "Invoice Inbox" },
  { test: (p) => p.startsWith("/reports"), title: "Reports" },
  { test: (p) => p.startsWith("/po/new"), title: "Upload Purchase Order" },
  { test: (p) => p.startsWith("/po/"), title: "Purchase Order Detail" },
  { test: (p) => p.startsWith("/po"), title: "Purchase Orders" },
  { test: (p) => p.startsWith("/suppliers"), title: "Supplier Accounts" },
  { test: (p) => p.startsWith("/email-inbox"), title: "Email Invoice Inbox" },
  { test: (p) => p.startsWith("/users"), title: "User Management" },
  { test: (p) => p.startsWith("/permissions"), title: "Roles & Permissions" },
  { test: (p) => p.startsWith("/workflows"), title: "Workflow Templates" },
];

function titleForPath(pathname) {
  const rule = TITLE_RULES.find((r) => r.test(pathname));
  return rule ? rule.title : "Dashboard";
}

function buildNavSections(role, pendingCount, permissions) {
  const sections = [
    {
      section: "DASHBOARDS",
      items: [
        { to: "/", end: true, label: "Analytics", icon: "📊" },
        { to: "/ap-visibility", label: "AP Visibility", icon: "🛰" },
        { to: "/ap", label: "Purchaser", icon: "📥" },
        { to: "/tax", label: "Tax Manager", icon: "🏛" },
        { to: "/auditor", label: "Auditor", icon: "🛡" },
      ],
    },
    {
      section: "APPROVALS",
      items: [
        { to: "/approvals", label: "My Approvals", icon: "✅", badge: pendingCount || null },
      ],
    },
    {
      section: "INVOICES",
      items: [
        { to: "/upload", label: "Upload Invoice", icon: "📤" },
        { to: "/invoices", label: "Invoice Inbox", icon: "📋" },
        { to: "/reports", label: "Reports", icon: "📈" },
      ],
    },
    // PROCUREMENT — hidden for now (for all roles). Routes still exist; re-add
    // these items to bring the section back.
    // {
    //   section: "PROCUREMENT",
    //   items: [
    //     { to: "/po/new", label: "Upload PO", icon: "📤" },
    //     { to: "/po", label: "Purchase Orders", icon: "📦", end: true, alsoActiveOn: (p) => p.startsWith("/po/") && p !== "/po/new" },
    //   ],
    // },
  ];

  // Admin section (each item is role-filtered below like everything else)
  sections.push({
    section: "ADMIN",
    items: [
      { to: "/users", label: "User Management", icon: "👥" },
      { to: "/permissions", label: "Roles & Permissions", icon: "🔐" },
      { to: "/suppliers", label: "Supplier Accounts", icon: "🏢" },
      { to: "/email-inbox", label: "Email Inbox", icon: "📬" },
      { to: "/workflows", label: "Workflows", icon: "⚡" },
      { to: "/tax-rules", label: "FBR Tax Rules", icon: "🏛" },
    ],
  });

  // Role-based visibility (live admin-editable matrix): keep only the items
  // this role may open, and drop sections that end up empty.
  return sections
    .map((s) => ({ ...s, items: s.items.filter((item) => canAccessPath(role, item.to, permissions)) }))
    .filter((s) => s.items.length > 0);
}

export default function Layout({ currentUser, pendingCount, onLogout, permissions }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const roleLabel = useRoleLabel();
  const location = useLocation();

  const NAV_SECTIONS = buildNavSections(currentUser.role, pendingCount, permissions);
  const pageTitle = titleForPath(location.pathname);
  const hideTopBar = location.pathname.startsWith("/results");

  // Keep the browser-tab title in sync with the current page + instance brand.
  useEffect(() => {
    document.title = pageDocumentTitle(pageTitle);
  }, [pageTitle]);

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 h-screen bg-neutral-900 text-neutral-300 flex flex-col transition-all duration-200 z-50 ${
          sidebarCollapsed ? "w-14" : "w-60"
        }`}
      >
        {/* Logo */}
        <div className="flex items-center justify-between px-3 h-14 border-b border-neutral-800">
          <div className="flex items-center gap-2 min-w-0">
            <img src={tmcLogo} alt="TMC" className="w-8 h-8 object-contain flex-shrink-0" />
            {!sidebarCollapsed && (
              <div className="flex flex-col leading-tight min-w-0">
                <span className="text-sm font-bold text-white tracking-wide">TMC</span>
                <span className="text-[10px] text-neutral-400 font-medium">eInvoice</span>
              </div>
            )}
          </div>
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="text-neutral-400 hover:text-white cursor-pointer bg-transparent border-none text-sm flex-shrink-0"
          >
            {sidebarCollapsed ? "▶" : "◀"}
          </button>
        </div>

        {/* Nav Sections */}
        <div className="flex-1 py-2 overflow-y-auto">
          {NAV_SECTIONS.map((section) => (
            <div key={section.section} className="py-3">
              {!sidebarCollapsed && (
                <div className="px-5 mb-2 text-[10px] font-semibold text-neutral-600 uppercase tracking-widest">
                  {section.section}
                </div>
              )}
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => {
                    const active = isActive || (item.alsoActiveOn ? item.alsoActiveOn(location.pathname) : false);
                    return `w-full flex items-center gap-3 py-2.5 text-xs font-medium cursor-pointer border-none transition-all duration-150 no-underline ${
                      sidebarCollapsed ? "justify-center px-0" : "px-5"
                    } ${
                      active
                        ? "bg-[rgba(79,98,242,0.12)] text-brand-400 border-l-[3px] border-l-brand-500 font-semibold"
                        : "bg-transparent text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200 border-l-[3px] border-l-transparent"
                    }`;
                  }}
                >
                  <span className="text-[15px]">{item.icon}</span>
                  {!sidebarCollapsed && <span>{item.label}</span>}
                  {!sidebarCollapsed && item.badge && (
                    <span className="ml-auto bg-danger-base text-white text-[10px] font-bold px-1.5 py-px rounded-full">
                      {item.badge}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </div>

        {/* Footer */}
        {!sidebarCollapsed && (
          <div className="px-5 py-3 border-t border-neutral-800 flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-white text-2xs font-bold flex-shrink-0">
              {currentUser?.name?.slice(0, 2).toUpperCase() || "??"}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-2xs font-semibold text-neutral-200 truncate">
                {currentUser?.name || "User"}
              </div>
              <div className="text-2xs text-neutral-500">
                {roleLabel(currentUser?.role) || "User"}
              </div>
            </div>
            <button
              onClick={onLogout}
              title="Sign out"
              className="text-neutral-500 hover:text-neutral-200 bg-transparent border-none cursor-pointer flex-shrink-0 transition-colors"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"/>
              </svg>
            </button>
          </div>
        )}
      </aside>

      {/* Main Content */}
      <div
        className={`flex-1 flex flex-col transition-all duration-200 ${
          sidebarCollapsed ? "ml-14" : "ml-60"
        }`}
      >
        {/* Top Bar */}
        {!hideTopBar && (
          <header className="sticky top-0 z-40 bg-neutral-0 border-b border-neutral-100 h-14 flex items-center justify-between px-6 shadow-xs">
            <h1 className="text-lg font-semibold text-neutral-900">{pageTitle}</h1>
            <NotificationBell />
          </header>
        )}

        {/* Page Content */}
        <main className="flex-1 p-6 bg-neutral-50">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

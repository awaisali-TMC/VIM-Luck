import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { getNotifications, markNotificationRead, markAllNotificationsRead } from "../../services/notificationService";

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const diff = (Date.now() - new Date(dateStr)) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function NotificationBell() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const load = useCallback(() => {
    if (document.hidden) return; // skip while the tab is backgrounded
    getNotifications()
      .then((d) => { setItems(d.notifications || []); setUnread(d.unread || 0); })
      .catch(() => {});
  }, []);

  // Poll every 60s; pause while the tab is hidden, refetch when it regains focus.
  useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    const onVisible = () => { if (!document.hidden) load(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const openItem = (n) => {
    setOpen(false);
    // Navigate first so nothing can block/delay it, then mark read in the background.
    if (n.entity_type === "invoice" && n.entity_id) {
      // Mention notifications come from comments — deep-link to the comment section.
      const hash = n.type === "mention" ? "#comments" : "";
      navigate(`/invoices/${n.entity_id}${hash}`);
    }
    if (!n.is_read) {
      markNotificationRead(n.id).then(load).catch(() => { /* ignore */ });
    }
  };

  const readAll = async () => {
    try { await markAllNotificationsRead(); } catch { /* ignore */ }
    load();
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative text-neutral-500 hover:text-neutral-800 bg-transparent border-none cursor-pointer p-1"
        title="Notifications"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 01-3.46 0" />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 bg-danger-base text-white text-[9px] font-bold min-w-[15px] h-[15px] px-1 rounded-full flex items-center justify-center">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 bg-white border border-neutral-200 rounded-md shadow-lg z-50 max-h-96 overflow-y-auto">
          <div className="flex items-center justify-between px-4 py-2 border-b border-neutral-100 sticky top-0 bg-white">
            <span className="text-xs font-semibold text-neutral-800">Notifications</span>
            {unread > 0 && (
              <button onClick={readAll} className="text-2xs text-brand-600 hover:text-brand-700 bg-transparent border-none cursor-pointer">
                Mark all read
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <div className="px-4 py-6 text-center text-2xs text-neutral-400">No notifications</div>
          ) : (
            items.map((n) => (
              <button
                key={n.id}
                onClick={() => openItem(n)}
                className={`w-full text-left px-4 py-2.5 border-b border-neutral-50 hover:bg-neutral-25 cursor-pointer block ${n.is_read ? "" : "bg-brand-50/40"}`}
              >
                <div className="flex items-start gap-2">
                  {!n.is_read && <span className="w-1.5 h-1.5 rounded-full bg-brand-500 mt-1.5 flex-shrink-0" />}
                  <div className={`flex-1 min-w-0 ${n.is_read ? "pl-3.5" : ""}`}>
                    <div className="text-2xs font-semibold text-neutral-800">{n.title}</div>
                    <div className="text-2xs text-neutral-500 leading-snug">{n.message}</div>
                    <div className="text-2xs text-neutral-400 mt-0.5">{timeAgo(n.created_at)}</div>
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

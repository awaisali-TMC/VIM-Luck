import { useState, useEffect, useCallback, useRef } from "react";
import api from "../../services/api";
import Card from "../common/Card";
import Button from "../common/Button";
import { useRoleLabel } from "../../config/roleLabels";

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
}

function getInitials(name) {
  return name ? name.split(" ").map((w) => w[0]).join("").toUpperCase().slice(0, 2) : "??";
}

const COLORS = [
  "bg-brand-500", "bg-emerald-500", "bg-amber-500", "bg-rose-500",
  "bg-violet-500", "bg-cyan-500", "bg-orange-500",
];

function authorColor(authorId) {
  return COLORS[(authorId || 0) % COLORS.length];
}

/** Render comment content with highlighted @mentions.
 *  Matches full display names (which can contain spaces) against the user list,
 *  so "@Tax Manager" highlights as one unit instead of just "@Tax". */
function CommentContent({ content, users = [] }) {
  const names = users.map((u) => u.display_name).filter(Boolean).sort((a, b) => b.length - a.length);
  let parts;
  let isMention;
  if (names.length) {
    const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`(@(?:${names.map(esc).join("|")}))`, "g");
    parts = content.split(re);
    const mentionSet = new Set(names.map((n) => `@${n}`));
    isMention = (p) => mentionSet.has(p);
  } else {
    parts = content.split(/(@\w+)/g);
    isMention = (p) => p.startsWith("@");
  }
  return (
    <p className="text-xs text-neutral-700 mt-0.5 mb-1 whitespace-pre-wrap">
      {parts.map((part, i) =>
        isMention(part) ? (
          <span key={i} className="bg-brand-50 text-brand-700 font-semibold px-1 rounded">
            {part}
          </span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </p>
  );
}

export default function CommentsCard({ entityType, entityId, currentUser }) {
  const roleLabel = useRoleLabel();
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newComment, setNewComment] = useState("");
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState(null);

  // @mention state
  const [users, setUsers] = useState([]);
  const [showMentions, setShowMentions] = useState(false);
  const [mentionQuery, setMentionQuery] = useState("");
  const [mentionIndex, setMentionIndex] = useState(0);
  const [mentionedIds, setMentionedIds] = useState([]);
  const [menuPos, setMenuPos] = useState(null);  // fixed-position anchor for the @menu
  const textareaRef = useRef(null);
  const mentionRef = useRef(null);

  // Fetch user list for @mentions (open to all internal users, unlike /api/admin/users)
  useEffect(() => {
    api.get("/api/comments/mentionable-users")
      .then((res) => setUsers(res.data.users || []))
      .catch(() => {});
  }, []);

  const fetchComments = useCallback(async () => {
    if (!entityType || !entityId) return;
    setLoading(true);
    try {
      const res = await api.get(`/api/comments/${entityType}/${entityId}`);
      setComments(res.data.comments || []);
    } catch {
      setComments([]);
    } finally {
      setLoading(false);
    }
  }, [entityType, entityId]);

  useEffect(() => { fetchComments(); }, [fetchComments]);

  // Filter users for mention dropdown
  const filteredUsers = mentionQuery
    ? users.filter((u) => {
        const q = mentionQuery.toLowerCase();
        return (
          u.display_name.toLowerCase().includes(q) ||
          u.email.toLowerCase().includes(q) ||
          (u.role || "").toLowerCase().includes(q) ||
          // the display name, which is what the list actually shows
          roleLabel(u.role).toLowerCase().includes(q)
        );
      })
    : users;

  const insertMention = (user) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const val = newComment;
    const cursorPos = textarea.selectionStart;

    // Find the @ trigger position
    let atPos = val.lastIndexOf("@", cursorPos - 1);
    if (atPos === -1) atPos = cursorPos;

    const before = val.slice(0, atPos);
    const after = val.slice(cursorPos);
    const mention = `@${user.display_name} `;

    setNewComment(before + mention + after);
    setShowMentions(false);
    setMentionQuery("");
    setMentionedIds((prev) => [...new Set([...prev, user.id])]);

    // Refocus textarea
    setTimeout(() => {
      textarea.focus();
      const newPos = before.length + mention.length;
      textarea.setSelectionRange(newPos, newPos);
    }, 0);
  };

  const handleInput = (e) => {
    const val = e.target.value;
    setNewComment(val);

    const cursorPos = e.target.selectionStart;
    const textBefore = val.slice(0, cursorPos);

    // Check if we're in an @mention context
    const lastAtIdx = textBefore.lastIndexOf("@");
    if (lastAtIdx !== -1) {
      const textAfterAt = textBefore.slice(lastAtIdx + 1);
      // Only show dropdown if @ is at start or preceded by space/newline, and no space break after query
      const charBefore = lastAtIdx > 0 ? textBefore[lastAtIdx - 1] : " ";
      if ((charBefore === " " || charBefore === "\n" || lastAtIdx === 0) && !textAfterAt.includes("\n")) {
        setMentionQuery(textAfterAt);
        setShowMentions(true);
        setMentionIndex(0);
        // Anchor the dropdown just below the textarea, in viewport (fixed)
        // coordinates so it escapes the Card's overflow-hidden clipping.
        const el = textareaRef.current;
        if (el) {
          const r = el.getBoundingClientRect();
          setMenuPos({ top: r.bottom + 4, left: r.left, width: r.width });
        }
        return;
      }
    }
    setShowMentions(false);
    setMentionQuery("");
  };

  const handleKeyDown = (e) => {
    if (showMentions && filteredUsers.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMentionIndex((prev) => Math.min(prev + 1, filteredUsers.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setMentionIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insertMention(filteredUsers[mentionIndex]);
        return;
      } else if (e.key === "Escape") {
        setShowMentions(false);
      }
    }
    // Enter posts the comment (Shift+Enter inserts a newline). When the
    // mention dropdown is open, Enter selects the user instead (handled above).
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handlePost();
    }
  };

  const handlePost = async () => {
    if (!newComment.trim()) return;
    setPosting(true);
    setError(null);

    // Extract mentioned user IDs from content
    const mentionNames = [...newComment.matchAll(/@([\w\s]+?)(?=\s@|\s*$|[.!?,])/g)].map((m) => m[1].trim());
    const resolvedIds = [...mentionedIds];
    for (const name of mentionNames) {
      const u = users.find((u) => u.display_name.toLowerCase() === name.toLowerCase());
      if (u && !resolvedIds.includes(u.id)) resolvedIds.push(u.id);
    }

    try {
      await api.post("/api/comments", {
        entity_type: entityType,
        entity_id: entityId,
        content: newComment.trim(),
        author_id: currentUser?.id || 0,
        author_name: currentUser?.name || "Unknown",
        author_role: currentUser?.role || null,
        mentioned_user_ids: resolvedIds.length > 0 ? resolvedIds : null,
        is_internal: 1,
      });
      setNewComment("");
      setMentionedIds([]);
      fetchComments();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to post comment");
    } finally {
      setPosting(false);
    }
  };

  const handleResolve = async (commentId, resolved) => {
    try {
      await api.patch(`/api/comments/${commentId}`, { is_resolved: resolved ? 1 : 0 });
      fetchComments();
    } catch { /* ignore */ }
  };

  const handleDelete = async (commentId) => {
    try {
      await api.delete(`/api/comments/${commentId}`);
      fetchComments();
    } catch { /* ignore */ }
  };

  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-neutral-900 m-0">
          Comments & Notes
        </h3>
        <span className="text-2xs text-neutral-500">
          {comments.length} comment{comments.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Comment input */}
      <div className="flex gap-2 mb-4">
        <div className={`w-7 h-7 rounded-full ${authorColor(currentUser?.id)} flex items-center justify-center text-white text-2xs font-bold flex-shrink-0`}>
          {getInitials(currentUser?.name)}
        </div>
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={newComment}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Add a comment... Type @ to tag a user"
            className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 focus:border-brand-400 outline-none resize-none"
            rows={2}
          />

          {/* @mention dropdown — fixed-position so it isn't clipped by the Card */}
          {showMentions && filteredUsers.length > 0 && menuPos && (
            <div
              ref={mentionRef}
              style={{ position: "fixed", top: menuPos.top, left: menuPos.left, width: menuPos.width }}
              className="bg-white border border-neutral-200 rounded-md shadow-lg z-50 max-h-48 overflow-y-auto"
            >
              {filteredUsers.slice(0, 8).map((user, i) => (
                <div
                  key={user.id}
                  onClick={() => insertMention(user)}
                  className={`flex items-center gap-2 px-3 py-2 cursor-pointer text-xs ${
                    i === mentionIndex ? "bg-brand-50" : "hover:bg-neutral-50"
                  }`}
                >
                  <div className={`w-6 h-6 rounded-full ${authorColor(user.id)} flex items-center justify-center text-white text-2xs font-bold`}>
                    {getInitials(user.display_name)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-neutral-800 truncate">{user.display_name}</div>
                    <div className="text-2xs text-neutral-400 truncate">
                      {roleLabel(user.role)}
                      {user.department && ` · ${user.department}`}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between mt-1">
            <span className="text-2xs text-neutral-400">Type @ to mention · Enter to post · Shift+Enter for a new line</span>
            <Button size="xs" onClick={handlePost} disabled={posting || !newComment.trim()}>
              {posting ? "Posting..." : "Post"}
            </Button>
          </div>
        </div>
      </div>

      {error && (
        <div className="text-2xs text-danger-dark mb-2">{error}</div>
      )}

      {/* Comment list */}
      {loading ? (
        <div className="text-center py-4 text-2xs text-neutral-400">Loading...</div>
      ) : comments.length === 0 ? (
        <div className="text-center py-4 text-2xs text-neutral-400">No comments yet. Be the first!</div>
      ) : (
        <div className="flex flex-col gap-3">
          {comments.map((c) => (
            <div key={c.id} className={`flex gap-2 ${c.is_resolved ? "opacity-60" : ""}`}>
              <div className={`w-7 h-7 rounded-full ${authorColor(c.author_id)} flex items-center justify-center text-white text-2xs font-bold flex-shrink-0 mt-0.5`}>
                {getInitials(c.author_name)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-2xs font-semibold text-neutral-800">{c.author_name}</span>
                  {c.author_role && (
                    <span className="text-2xs text-neutral-400">{roleLabel(c.author_role)}</span>
                  )}
                  <span className="text-2xs text-neutral-400">{timeAgo(c.created_at)}</span>
                  {c.is_resolved === 1 && (
                    <span className="text-2xs text-emerald-600 font-semibold">✓ Resolved</span>
                  )}
                </div>
                <CommentContent content={c.content} users={users} />
                <div className="flex items-center gap-2">
                  {c.is_resolved !== 1 ? (
                    <button
                      onClick={() => handleResolve(c.id, true)}
                      className="text-2xs text-neutral-400 hover:text-emerald-600 bg-transparent border-none cursor-pointer"
                    >
                      Resolve
                    </button>
                  ) : (
                    <button
                      onClick={() => handleResolve(c.id, false)}
                      className="text-2xs text-neutral-400 hover:text-amber-600 bg-transparent border-none cursor-pointer"
                    >
                      Unresolve
                    </button>
                  )}
                  {(currentUser?.id === c.author_id || currentUser?.role === "admin") && (
                    <button
                      onClick={() => handleDelete(c.id)}
                      className="text-2xs text-neutral-400 hover:text-danger-base bg-transparent border-none cursor-pointer"
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

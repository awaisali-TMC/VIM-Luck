import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../utils/colors';
import { getInvoiceComments, addInvoiceComment } from '../services/analyticsService';

interface Comment {
  id: number;
  text: string;
  author_name: string;
  author_role?: string;
  created_at: string;
}

interface Props {
  invoiceId: number;
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  const now = new Date();
  const diff = (now.getTime() - d.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
}

export default function CommentsSection({ invoiceId }: Props) {
  const [comments, setComments] = useState<Comment[]>([]);
  const [loading, setLoading] = useState(true);
  const [newComment, setNewComment] = useState('');
  const [sending, setSending] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    loadComments();
  }, [invoiceId]);

  const loadComments = async () => {
    try {
      const data = await getInvoiceComments(invoiceId);
      setComments(Array.isArray(data) ? data : []);
    } catch {
      setComments([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async () => {
    if (!newComment.trim()) return;
    setSending(true);
    try {
      await addInvoiceComment(invoiceId, newComment.trim());
      setNewComment('');
      await loadComments();
    } catch (err: any) {
      Alert.alert('Error', err?.response?.data?.detail || 'Failed to add comment');
    } finally {
      setSending(false);
    }
  };

  return (
    <View style={styles.container}>
      <TouchableOpacity style={styles.headerRow} onPress={() => setExpanded(!expanded)}>
        <View style={styles.headerLeft}>
          <Ionicons name="chatbubble-ellipses" size={16} color={colors.brand[500]} />
          <Text style={styles.title}>Comments</Text>
          {comments.length > 0 && (
            <View style={styles.countBadge}>
              <Text style={styles.countText}>{comments.length}</Text>
            </View>
          )}
        </View>
        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={16}
          color={colors.neutral[400]}
        />
      </TouchableOpacity>

      {expanded && (
        <View style={styles.expandedSection}>
          {loading ? (
            <ActivityIndicator size="small" color={colors.brand[500]} style={{ padding: 16 }} />
          ) : comments.length === 0 ? (
            <Text style={styles.emptyText}>No comments yet</Text>
          ) : (
            comments.map((c) => (
              <View key={c.id} style={styles.commentItem}>
                <View style={styles.commentAvatar}>
                  <Ionicons name="person" size={12} color={colors.neutral[500]} />
                </View>
                <View style={{ flex: 1 }}>
                  <View style={styles.commentHeader}>
                    <Text style={styles.commentAuthor}>{c.author_name}</Text>
                    {c.author_role && (
                      <Text style={styles.commentRole}>{c.author_role.replace(/_/g, ' ')}</Text>
                    )}
                    <Text style={styles.commentTime}>{timeAgo(c.created_at)}</Text>
                  </View>
                  <Text style={styles.commentText}>{c.text}</Text>
                </View>
              </View>
            ))
          )}

          {/* New Comment */}
          <View style={styles.inputRow}>
            <TextInput
              style={styles.input}
              placeholder="Write a comment..."
              placeholderTextColor={colors.neutral[400]}
              value={newComment}
              onChangeText={setNewComment}
              multiline
            />
            <TouchableOpacity
              style={[styles.sendBtn, !newComment.trim() && styles.sendBtnDisabled]}
              onPress={handleSend}
              disabled={!newComment.trim() || sending}
            >
              {sending ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Ionicons name="send" size={16} color="#fff" />
              )}
            </TouchableOpacity>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#fff',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    marginBottom: 12,
    overflow: 'hidden',
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 14,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  title: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.neutral[800],
  },
  countBadge: {
    backgroundColor: colors.brand[500],
    borderRadius: 10,
    minWidth: 18,
    height: 18,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 5,
  },
  countText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#fff',
  },
  expandedSection: {
    paddingHorizontal: 14,
    paddingBottom: 14,
  },
  emptyText: {
    fontSize: 12,
    color: colors.neutral[400],
    textAlign: 'center',
    paddingVertical: 12,
  },
  commentItem: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 10,
  },
  commentAvatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.neutral[100],
    alignItems: 'center',
    justifyContent: 'center',
  },
  commentHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 2,
  },
  commentAuthor: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.neutral[800],
  },
  commentRole: {
    fontSize: 9,
    fontWeight: '600',
    color: colors.brand[500],
    textTransform: 'capitalize',
  },
  commentTime: {
    fontSize: 9,
    color: colors.neutral[400],
  },
  commentText: {
    fontSize: 12,
    color: colors.neutral[700],
    lineHeight: 17,
  },
  inputRow: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'flex-end',
    marginTop: 8,
    borderTopWidth: 1,
    borderTopColor: colors.neutral[100],
    paddingTop: 10,
  },
  input: {
    flex: 1,
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 12,
    color: colors.neutral[800],
    minHeight: 36,
    maxHeight: 80,
  },
  sendBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.brand[500],
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtnDisabled: {
    opacity: 0.5,
  },
});

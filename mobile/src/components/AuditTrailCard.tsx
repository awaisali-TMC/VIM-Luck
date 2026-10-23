import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../utils/colors';
import { getEntityAuditLogs } from '../services/analyticsService';

interface AuditEntry {
  id: number;
  action: string;
  actor_name: string;
  actor_type: string;
  old_value: string | null;
  new_value: string | null;
  created_at: string;
}

interface Props {
  entityType: string;
  entityId: number;
}

const ACTION_CONFIG: Record<string, { icon: keyof typeof Ionicons.glyphMap; color: string }> = {
  created: { icon: 'add-circle', color: colors.brand[500] },
  updated: { icon: 'create', color: colors.info[500] },
  status_changed: { icon: 'swap-horizontal', color: colors.warning[500] },
  approved: { icon: 'checkmark-circle', color: colors.success[500] },
  rejected: { icon: 'close-circle', color: colors.danger[500] },
  returned: { icon: 'return-down-back', color: colors.warning[600] },
  comment_added: { icon: 'chatbubble', color: colors.brand[400] },
  classified: { icon: 'sparkles', color: '#8B5CF6' },
};

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

export default function AuditTrailCard({ entityType, entityId }: Props) {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    getEntityAuditLogs(entityType, entityId)
      .then((data) => setEntries(Array.isArray(data) ? data : []))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, [entityType, entityId]);

  if (loading) return null;
  if (entries.length === 0) return null;

  const displayed = expanded ? entries : entries.slice(0, 3);

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Ionicons name="time" size={16} color={colors.brand[500]} />
        <Text style={styles.title}>Audit Trail</Text>
        <View style={styles.countBadge}>
          <Text style={styles.countText}>{entries.length}</Text>
        </View>
      </View>

      {displayed.map((entry, i) => {
        const cfg = ACTION_CONFIG[entry.action] || { icon: 'ellipse', color: colors.neutral[400] };
        return (
          <View key={entry.id} style={styles.entryRow}>
            <View style={styles.timeline}>
              <View style={[styles.dot, { backgroundColor: cfg.color }]}>
                <Ionicons name={cfg.icon} size={10} color="#fff" />
              </View>
              {i < displayed.length - 1 && <View style={styles.line} />}
            </View>
            <View style={styles.entryContent}>
              <Text style={styles.entryAction}>
                <Text style={styles.entryActorName}>{entry.actor_name || 'System'}</Text>
                {' '}{entry.action.replace(/_/g, ' ')}
              </Text>
              <Text style={styles.entryTime}>{timeAgo(entry.created_at)}</Text>
            </View>
          </View>
        );
      })}

      {entries.length > 3 && (
        <TouchableOpacity style={styles.toggleBtn} onPress={() => setExpanded(!expanded)}>
          <Text style={styles.toggleText}>
            {expanded ? 'Show Less' : `Show All (${entries.length})`}
          </Text>
          <Ionicons
            name={expanded ? 'chevron-up' : 'chevron-down'}
            size={14}
            color={colors.brand[500]}
          />
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    marginBottom: 12,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 12,
  },
  title: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.neutral[800],
    flex: 1,
  },
  countBadge: {
    backgroundColor: colors.neutral[200],
    borderRadius: 8,
    minWidth: 18,
    height: 18,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 5,
  },
  countText: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.neutral[600],
  },
  entryRow: {
    flexDirection: 'row',
    marginBottom: 0,
  },
  timeline: {
    alignItems: 'center',
    width: 24,
  },
  dot: {
    width: 18,
    height: 18,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
  },
  line: {
    width: 2,
    flex: 1,
    backgroundColor: colors.neutral[200],
    marginVertical: 2,
  },
  entryContent: {
    flex: 1,
    paddingLeft: 8,
    paddingBottom: 12,
  },
  entryAction: {
    fontSize: 11,
    color: colors.neutral[600],
    lineHeight: 16,
  },
  entryActorName: {
    fontWeight: '700',
    color: colors.neutral[800],
  },
  entryTime: {
    fontSize: 9,
    color: colors.neutral[400],
    marginTop: 2,
  },
  toggleBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingTop: 4,
  },
  toggleText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.brand[500],
  },
});

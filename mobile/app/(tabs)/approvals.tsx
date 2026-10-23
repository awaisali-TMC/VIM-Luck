import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, statusColors } from '../../src/utils/colors';
import { fmtAmount } from '../../src/utils/formatters';
import { getInvoices } from '../../src/services/invoiceService';
import StatusBadge from '../../src/components/StatusBadge';
import type { InvoiceListItem } from '../../src/types';

type TabKey = 'action' | 'progress' | 'completed' | 'all';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'action', label: 'Action Needed' },
  { key: 'progress', label: 'In Progress' },
  { key: 'completed', label: 'Completed' },
  { key: 'all', label: 'All' },
];

const STATUS_EVENTS: Record<string, { icon: keyof typeof Ionicons.glyphMap; text: string; color: string }> = {
  draft: { icon: 'create-outline', text: 'Invoice created as draft', color: '#94A3B8' },
  pending_processing: { icon: 'time-outline', text: 'Submitted for AI processing', color: '#F59E0B' },
  validated: { icon: 'checkmark-circle-outline', text: 'AI validation complete', color: '#3B82F6' },
  pending_approval: { icon: 'hourglass-outline', text: 'Sent for approval', color: '#8B5CF6' },
  approved: { icon: 'checkmark-done-circle-outline', text: 'Invoice approved', color: '#10B981' },
  rejected: { icon: 'close-circle-outline', text: 'Invoice rejected', color: '#EF4444' },
  exception: { icon: 'warning-outline', text: 'Exception flagged', color: '#EF4444' },
  posted: { icon: 'checkmark-done-circle', text: 'Posted to ERP', color: '#059669' },
};

function timeAgo(dateStr: string | null): string {
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

export default function ApprovalsScreen() {
  const router = useRouter();
  const [invoices, setInvoices] = useState<InvoiceListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>('action');

  const loadInvoices = useCallback(async () => {
    try {
      const data = await getInvoices(0, 100);
      setInvoices(data.invoices || []);
    } catch {
      setInvoices([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadInvoices();
  }, [loadInvoices]);

  const onRefresh = () => {
    setRefreshing(true);
    loadInvoices();
  };

  // Categorize
  const actionNeeded = invoices.filter((inv) =>
    ['exception', 'rejected'].includes(inv.status)
  );
  const inProgress = invoices.filter((inv) =>
    ['pending_processing', 'validated', 'pending_approval'].includes(inv.status)
  );
  const completed = invoices.filter((inv) =>
    ['approved', 'posted'].includes(inv.status)
  );

  const getFilteredInvoices = (): InvoiceListItem[] => {
    switch (activeTab) {
      case 'action': return actionNeeded;
      case 'progress': return inProgress;
      case 'completed': return completed;
      default: return invoices;
    }
  };

  const filtered = getFilteredInvoices();

  return (
    <View style={styles.container}>
      {/* Summary KPIs */}
      <View style={styles.kpiRow}>
        <View style={[styles.kpiCard, { backgroundColor: colors.danger[50] }]}>
          <Ionicons name="warning" size={16} color={colors.danger[500]} />
          <Text style={[styles.kpiValue, { color: colors.danger[700] }]}>{actionNeeded.length}</Text>
          <Text style={styles.kpiLabel}>Action</Text>
        </View>
        <View style={[styles.kpiCard, { backgroundColor: colors.warning[50] }]}>
          <Ionicons name="time" size={16} color={colors.warning[500]} />
          <Text style={[styles.kpiValue, { color: colors.warning[700] }]}>{inProgress.length}</Text>
          <Text style={styles.kpiLabel}>Progress</Text>
        </View>
        <View style={[styles.kpiCard, { backgroundColor: colors.success[50] }]}>
          <Ionicons name="checkmark-circle" size={16} color={colors.success[500]} />
          <Text style={[styles.kpiValue, { color: colors.success[700] }]}>{completed.length}</Text>
          <Text style={styles.kpiLabel}>Done</Text>
        </View>
        <View style={[styles.kpiCard, { backgroundColor: colors.brand[50] }]}>
          <Ionicons name="document-text" size={16} color={colors.brand[500]} />
          <Text style={[styles.kpiValue, { color: colors.brand[700] }]}>{invoices.length}</Text>
          <Text style={styles.kpiLabel}>Total</Text>
        </View>
      </View>

      {/* Tabs */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabsScroll}>
        <View style={styles.tabsRow}>
          {TABS.map((tab) => (
            <TouchableOpacity
              key={tab.key}
              style={[styles.tab, activeTab === tab.key && styles.tabActive]}
              onPress={() => setActiveTab(tab.key)}
            >
              <Text style={[styles.tabText, activeTab === tab.key && styles.tabTextActive]}>
                {tab.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>

      {/* List */}
      {loading ? (
        <View style={styles.centerLoader}>
          <ActivityIndicator size="large" color={colors.brand[500]} />
        </View>
      ) : (
        <ScrollView
          style={styles.list}
          contentContainerStyle={styles.listContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        >
          {filtered.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="checkmark-done-circle-outline" size={48} color={colors.neutral[300]} />
              <Text style={styles.emptyText}>No invoices in this category</Text>
            </View>
          ) : (
            filtered.map((inv) => {
              const evt = STATUS_EVENTS[inv.status] || STATUS_EVENTS.draft;
              return (
                <TouchableOpacity
                  key={inv.id}
                  style={styles.card}
                  onPress={() => router.push(`/invoice/${inv.id}`)}
                  activeOpacity={0.7}
                >
                  <View style={styles.cardLeft}>
                    <View style={[styles.statusDot, { backgroundColor: evt.color }]} />
                  </View>
                  <View style={styles.cardContent}>
                    <View style={styles.cardTop}>
                      <Text style={styles.cardInvNum} numberOfLines={1}>
                        {inv.invoice_number ? `#${inv.invoice_number}` : `Invoice #${inv.id}`}
                      </Text>
                      <StatusBadge status={inv.status} />
                    </View>
                    <Text style={styles.cardEvent}>{evt.text}</Text>
                    <View style={styles.cardMeta}>
                      <Text style={styles.cardMetaText}>
                        {inv.supplier_name || 'Unknown'}
                      </Text>
                      <Text style={styles.cardMetaDot}>·</Text>
                      <Text style={styles.cardMetaText}>
                        {inv.currency || 'PKR'} {fmtAmount(inv.total_amount)}
                      </Text>
                      <Text style={styles.cardMetaDot}>·</Text>
                      <Text style={styles.cardMetaTime}>{timeAgo(inv.created_at)}</Text>
                    </View>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={colors.neutral[300]} />
                </TouchableOpacity>
              );
            })
          )}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.neutral[50],
  },
  kpiRow: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
    gap: 8,
  },
  kpiCard: {
    flex: 1,
    alignItems: 'center',
    borderRadius: 12,
    paddingVertical: 10,
    gap: 4,
  },
  kpiValue: {
    fontSize: 18,
    fontWeight: '800',
  },
  kpiLabel: {
    fontSize: 9,
    fontWeight: '600',
    color: colors.neutral[500],
    textTransform: 'uppercase',
  },
  tabsScroll: {
    maxHeight: 44,
    paddingHorizontal: 16,
  },
  tabsRow: {
    flexDirection: 'row',
    gap: 6,
    paddingVertical: 6,
  },
  tab: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 20,
    backgroundColor: colors.neutral[100],
  },
  tabActive: {
    backgroundColor: colors.brand[500],
  },
  tabText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.neutral[500],
  },
  tabTextActive: {
    color: '#fff',
  },
  centerLoader: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  list: {
    flex: 1,
  },
  listContent: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 24,
  },
  emptyState: {
    alignItems: 'center',
    paddingVertical: 48,
    gap: 12,
  },
  emptyText: {
    fontSize: 14,
    color: colors.neutral[400],
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 14,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    gap: 10,
  },
  cardLeft: {
    alignItems: 'center',
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  cardContent: {
    flex: 1,
  },
  cardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  cardInvNum: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.neutral[800],
    flex: 1,
    marginRight: 8,
  },
  cardEvent: {
    fontSize: 11,
    color: colors.neutral[500],
    marginBottom: 4,
  },
  cardMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  cardMetaText: {
    fontSize: 10,
    color: colors.neutral[400],
  },
  cardMetaDot: {
    fontSize: 10,
    color: colors.neutral[300],
  },
  cardMetaTime: {
    fontSize: 10,
    color: colors.neutral[400],
  },
});

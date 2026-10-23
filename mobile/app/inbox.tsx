import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  ScrollView,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../src/utils/colors';
import { fmtDate } from '../src/utils/formatters';
import { listEmails, fetchEmailsFromServer, getInboxConfig } from '../src/services/emailService';
import EmptyState from '../src/components/EmptyState';
import { SkeletonCard } from '../src/components/SkeletonLoader';
import type { EmailMessage, EmailConfig, EmailStatus } from '../src/types';

const TABS = [
  { key: 'all', label: 'All' },
  { key: 'unread', label: 'Unread' },
  { key: 'attachments', label: 'Attachments' },
  { key: 'processed', label: 'Processed' },
] as const;

export default function InboxScreen() {
  const router = useRouter();
  const [emails, setEmails] = useState<EmailMessage[]>([]);
  const [stats, setStats] = useState({ total: 0, unread: 0, with_attachments: 0, processed: 0 });
  const [config, setConfig] = useState<EmailConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [activeTab, setActiveTab] = useState<string>('all');

  const loadEmails = useCallback(async (isRefresh = false) => {
    try {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);

      const [emailData, configData] = await Promise.all([
        listEmails(0, 50),
        getInboxConfig(),
      ]);
      setEmails(emailData.emails || []);
      setStats({
        total: emailData.total,
        unread: emailData.unread,
        with_attachments: emailData.with_attachments,
        processed: emailData.processed,
      });
      setConfig(configData);
    } catch {
      // silently handle
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadEmails(); }, [loadEmails]);

  const handleFetch = async () => {
    if (fetching) return;
    try {
      setFetching(true);
      const result = await fetchEmailsFromServer();
      Alert.alert(
        'Fetch Complete',
        `Fetched: ${result.fetched}, Saved: ${result.saved}, Skipped: ${result.skipped}`,
      );
      await loadEmails();
    } catch (err: any) {
      Alert.alert('Error', err.response?.data?.detail || err.message || 'Failed to fetch emails.');
    } finally {
      setFetching(false);
    }
  };

  const filteredEmails = emails.filter((e) => {
    if (activeTab === 'unread') return e.status === 'unread';
    if (activeTab === 'attachments') return e.has_attachments;
    if (activeTab === 'processed') return e.status === 'processed';
    return true;
  });

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
          <Ionicons name="arrow-back" size={22} color={colors.neutral[700]} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Email Inbox</Text>
        <TouchableOpacity onPress={handleFetch} disabled={fetching} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
          {fetching ? (
            <ActivityIndicator size="small" color={colors.brand[500]} />
          ) : (
            <Ionicons name="refresh" size={20} color={colors.brand[500]} />
          )}
        </TouchableOpacity>
      </View>

      {/* Config status — subtle inline */}
      {config && (
        <View style={styles.configRow}>
          <Ionicons
            name={config.configured ? 'checkmark-circle' : 'alert-circle'}
            size={14}
            color={config.configured ? colors.success[500] : colors.warning[500]}
          />
          <Text style={styles.configText}>
            {config.configured ? config.gmail_address : 'Gmail not configured'}
          </Text>
        </View>
      )}

      {/* KPI Row */}
      <View style={styles.kpiRow}>
        <View style={[styles.kpiCard, { backgroundColor: colors.brand[50] }]}>
          <Ionicons name="mail" size={16} color={colors.brand[500]} />
          <Text style={[styles.kpiValue, { color: colors.brand[700] }]}>{stats.total}</Text>
          <Text style={styles.kpiLabel}>Total</Text>
        </View>
        <View style={[styles.kpiCard, { backgroundColor: colors.info[50] }]}>
          <Ionicons name="mail-unread" size={16} color={colors.info[500]} />
          <Text style={[styles.kpiValue, { color: colors.info[700] }]}>{stats.unread}</Text>
          <Text style={styles.kpiLabel}>Unread</Text>
        </View>
        <View style={[styles.kpiCard, { backgroundColor: colors.warning[50] }]}>
          <Ionicons name="attach" size={16} color={colors.warning[500]} />
          <Text style={[styles.kpiValue, { color: colors.warning[700] }]}>{stats.with_attachments}</Text>
          <Text style={styles.kpiLabel}>Files</Text>
        </View>
        <View style={[styles.kpiCard, { backgroundColor: colors.success[50] }]}>
          <Ionicons name="checkmark-circle" size={16} color={colors.success[500]} />
          <Text style={[styles.kpiValue, { color: colors.success[700] }]}>{stats.processed}</Text>
          <Text style={styles.kpiLabel}>Done</Text>
        </View>
      </View>

      {/* Tabs */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabsScroll}>
        <View style={styles.tabsRow}>
          {TABS.map((tab) => {
            const active = activeTab === tab.key;
            return (
              <TouchableOpacity
                key={tab.key}
                style={[styles.tab, active && styles.tabActive]}
                onPress={() => setActiveTab(tab.key)}
              >
                <Text style={[styles.tabText, active && styles.tabTextActive]}>{tab.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </ScrollView>

      {/* List */}
      {loading ? (
        <View style={styles.listContent}>
          {[1, 2, 3, 4, 5].map((i) => <SkeletonCard key={i} />)}
        </View>
      ) : filteredEmails.length === 0 ? (
        <View style={styles.listContent}>
          <EmptyState
            icon="mail-outline"
            title="No emails"
            description={activeTab === 'all' ? 'Tap refresh to fetch emails from Gmail.' : 'No emails match this filter.'}
          />
        </View>
      ) : (
        <FlatList
          style={styles.list}
          contentContainerStyle={styles.listContent}
          data={filteredEmails}
          keyExtractor={(item) => String(item.id)}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={styles.card}
              onPress={() => router.push(`/email/${item.id}`)}
              activeOpacity={0.7}
            >
              <View style={styles.cardLeft}>
                <View
                  style={[
                    styles.statusDot,
                    {
                      backgroundColor:
                        item.status === 'unread'
                          ? colors.brand[500]
                          : item.status === 'processed'
                          ? colors.success[500]
                          : colors.neutral[300],
                    },
                  ]}
                />
              </View>
              <View style={styles.cardContent}>
                <View style={styles.cardTop}>
                  <Text
                    style={[styles.cardFrom, item.status === 'unread' && styles.cardFromBold]}
                    numberOfLines={1}
                  >
                    {item.from_address}
                  </Text>
                  {item.has_attachments && (
                    <Ionicons name="attach" size={14} color={colors.neutral[400]} />
                  )}
                </View>
                <Text
                  style={[styles.cardSubject, item.status === 'unread' && styles.cardSubjectBold]}
                  numberOfLines={1}
                >
                  {item.subject || '(no subject)'}
                </Text>
                <Text style={styles.cardDate}>{fmtDate(item.received_at)}</Text>
              </View>
              <Ionicons name="chevron-forward" size={16} color={colors.neutral[300]} />
            </TouchableOpacity>
          )}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => loadEmails(true)} tintColor={colors.brand[500]} />
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.neutral[50],
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 52,
    paddingBottom: 12,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[100],
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.neutral[900],
  },
  configRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 16,
    paddingVertical: 6,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[100],
  },
  configText: {
    fontSize: 11,
    color: colors.neutral[500],
  },

  // KPIs — same pattern as approvals
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

  // Tabs — same pattern as approvals
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

  // List — same pattern as approvals
  list: {
    flex: 1,
  },
  listContent: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 24,
  },

  // Card — matches approvals card style
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
    marginBottom: 2,
  },
  cardFrom: {
    fontSize: 13,
    color: colors.neutral[700],
    flex: 1,
    marginRight: 8,
  },
  cardFromBold: {
    fontWeight: '700',
    color: colors.neutral[900],
  },
  cardSubject: {
    fontSize: 12,
    color: colors.neutral[500],
    marginBottom: 4,
  },
  cardSubjectBold: {
    fontWeight: '600',
    color: colors.neutral[700],
  },
  cardDate: {
    fontSize: 10,
    color: colors.neutral[400],
  },
});

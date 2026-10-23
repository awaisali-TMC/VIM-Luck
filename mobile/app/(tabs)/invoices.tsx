import React, { useState, useEffect } from 'react';
import { View, Text, FlatList, StyleSheet, RefreshControl, ScrollView, TouchableOpacity, BackHandler } from 'react-native';
import { useRouter, useLocalSearchParams, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../../src/utils/colors';
import useInvoices from '../../src/hooks/useInvoices';
import InvoiceCard from '../../src/components/InvoiceCard';
import EmptyState from '../../src/components/EmptyState';
import { SkeletonCard } from '../../src/components/SkeletonLoader';

const STATUS_TABS = [
  { key: undefined, label: 'All' },
  { key: 'draft', label: 'Draft' },
  { key: 'pending_processing', label: 'Processing' },
  { key: 'validated', label: 'Validated' },
  { key: 'pending_approval', label: 'Approval' },
  { key: 'approved', label: 'Approved' },
  { key: 'posted', label: 'Posted' },
  { key: 'exception', label: 'Exception' },
  { key: 'rejected', label: 'Rejected' },
] as const;

export default function InvoicesScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ status?: string; newIds?: string }>();
  const [activeTab, setActiveTab] = useState<string | undefined>(params.status || undefined);

  // Freshly-uploaded drafts (from a batch / multi-invoice upload) to highlight.
  const newIds = React.useMemo(() => {
    const ids = (params.newIds || '')
      .split(',')
      .map((s) => parseInt(s, 10))
      .filter((n) => !Number.isNaN(n));
    return new Set(ids);
  }, [params.newIds]);

  // When route params change (navigated from home KPI), update the tab
  useEffect(() => {
    if (params.status) setActiveTab(params.status);
  }, [params.status]);

  // Override Android back to return to home instead of falling through to the upload tab
  useFocusEffect(
    React.useCallback(() => {
      const handler = BackHandler.addEventListener('hardwareBackPress', () => {
        router.replace('/home');
        return true;
      });
      return () => handler.remove();
    }, [router])
  );

  const { invoices, total, loading, refreshing, refresh, loadMore, hasMore } = useInvoices(activeTab);

  return (
    <View style={styles.wrapper}>
      {/* Tabs */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.tabsScroll}
        contentContainerStyle={styles.tabsContent}
      >
        {STATUS_TABS.map((tab) => {
          const active = activeTab === tab.key;
          return (
            <TouchableOpacity
              key={tab.label}
              style={[styles.tab, active && styles.tabActive]}
              onPress={() => setActiveTab(tab.key)}
            >
              <Text style={[styles.tabText, active && styles.tabTextActive]}>{tab.label}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      {/* Just-uploaded banner (batch / multi-invoice upload) */}
      {newIds.size > 0 && (
        <View style={styles.uploadBanner}>
          <Ionicons name="checkmark-circle" size={16} color={colors.success[600]} />
          <Text style={styles.uploadBannerText}>
            {newIds.size} invoice{newIds.size !== 1 ? 's' : ''} just uploaded as draft{newIds.size !== 1 ? 's' : ''} — highlighted below. Open each to review.
          </Text>
        </View>
      )}

      {/* Count */}
      <View style={styles.countRow}>
        <Text style={styles.countText}>
          {total} invoice{total !== 1 ? 's' : ''}
          {activeTab ? ` · ${activeTab.replace(/_/g, ' ')}` : ''}
        </Text>
      </View>

      {/* List */}
      {loading && invoices.length === 0 ? (
        <View style={styles.container}>
          {[1, 2, 3, 4, 5].map((i) => (
            <SkeletonCard key={i} />
          ))}
        </View>
      ) : !loading && invoices.length === 0 ? (
        <View style={styles.container}>
          <EmptyState
            icon="document-text-outline"
            title="No invoices"
            description={activeTab ? `No invoices with status "${activeTab.replace(/_/g, ' ')}".` : 'Upload your first invoice to get started.'}
          />
        </View>
      ) : (
        <FlatList
          style={styles.list}
          contentContainerStyle={styles.container}
          data={invoices}
          keyExtractor={(item) => String(item.id)}
          renderItem={({ item }) => (
            <InvoiceCard
              invoice={item}
              highlighted={newIds.has(item.id)}
              onPress={() => router.push(`/invoice/${item.id}`)}
            />
          )}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={refresh}
              tintColor={colors.brand[500]}
            />
          }
          onEndReached={hasMore ? loadMore : undefined}
          onEndReachedThreshold={0.3}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    flex: 1,
    backgroundColor: colors.neutral[50],
  },
  list: {
    flex: 1,
  },
  container: {
    padding: 16,
  },
  tabsScroll: {
    maxHeight: 44,
    paddingHorizontal: 16,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[100],
  },
  tabsContent: {
    flexDirection: 'row',
    gap: 6,
    paddingVertical: 6,
  },
  tab: {
    paddingHorizontal: 12,
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
  uploadBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginHorizontal: 16,
    marginTop: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: colors.success[50],
    borderWidth: 1,
    borderColor: colors.success[200],
  },
  uploadBannerText: {
    flex: 1,
    fontSize: 12,
    fontWeight: '600',
    color: colors.success[700],
  },
  countRow: {
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  countText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.neutral[400],
    textTransform: 'capitalize',
  },
});

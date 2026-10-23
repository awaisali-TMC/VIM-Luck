import React, { useState } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  RefreshControl,
  TouchableOpacity,
  ScrollView,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as DocumentPicker from 'expo-document-picker';
import { colors } from '../src/utils/colors';
import { hapticLight } from '../src/utils/haptics';
import usePurchaseOrders from '../src/hooks/usePurchaseOrders';
import POCard from '../src/components/POCard';
import EmptyState from '../src/components/EmptyState';
import { SkeletonCard } from '../src/components/SkeletonLoader';

const TABS = [
  { key: undefined, label: 'All' },
  { key: 'open', label: 'Open' },
  { key: 'partially_received', label: 'Partial' },
  { key: 'fully_received', label: 'Received' },
  { key: 'closed', label: 'Closed' },
] as const;

export default function PurchaseOrdersScreen() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<string | undefined>(undefined);
  const { orders, total, loading, refreshing, refresh, loadMore, hasMore } =
    usePurchaseOrders(activeTab);

  const handleScanPO = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: ['application/pdf', 'image/jpeg', 'image/png'],
        copyToCacheDirectory: true,
      });
      if (res.canceled || !res.assets?.[0]) return;
      hapticLight();
      Alert.alert(
        'PO Document Selected',
        `${res.assets[0].name}\n\nAI-based PO extraction is coming soon. For now, please create the PO manually.`,
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Create Manually', onPress: () => router.push('/po/create') },
        ],
      );
    } catch {
      Alert.alert('Error', 'Failed to pick document.');
    }
  };

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
          <Ionicons name="arrow-back" size={22} color={colors.neutral[700]} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Purchase Orders</Text>
        <View style={styles.headerRight}>
          <TouchableOpacity onPress={handleScanPO} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="scan-outline" size={20} color={colors.brand[500]} />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => router.push('/po/create')} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="add-circle-outline" size={22} color={colors.brand[500]} />
          </TouchableOpacity>
        </View>
      </View>

      {/* KPI Row — matches Approvals pattern */}
      <View style={styles.kpiRow}>
        <View style={[styles.kpiCard, { backgroundColor: colors.brand[50] }]}>
          <Ionicons name="cart" size={16} color={colors.brand[500]} />
          <Text style={[styles.kpiValue, { color: colors.brand[700] }]}>{total}</Text>
          <Text style={styles.kpiLabel}>Total</Text>
        </View>
        <View style={[styles.kpiCard, { backgroundColor: colors.info[50] }]}>
          <Ionicons name="open" size={16} color={colors.info[500]} />
          <Text style={[styles.kpiValue, { color: colors.info[700] }]}>
            {orders.filter((o) => o.status === 'open').length}
          </Text>
          <Text style={styles.kpiLabel}>Open</Text>
        </View>
        <View style={[styles.kpiCard, { backgroundColor: colors.warning[50] }]}>
          <Ionicons name="swap-horizontal" size={16} color={colors.warning[500]} />
          <Text style={[styles.kpiValue, { color: colors.warning[700] }]}>
            {orders.filter((o) => o.status === 'partially_received').length}
          </Text>
          <Text style={styles.kpiLabel}>Partial</Text>
        </View>
        <View style={[styles.kpiCard, { backgroundColor: colors.success[50] }]}>
          <Ionicons name="checkmark-circle" size={16} color={colors.success[500]} />
          <Text style={[styles.kpiValue, { color: colors.success[700] }]}>
            {orders.filter((o) => o.status === 'fully_received').length}
          </Text>
          <Text style={styles.kpiLabel}>Received</Text>
        </View>
      </View>

      {/* Tabs — matches Approvals pattern */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabsScroll}>
        <View style={styles.tabsRow}>
          {TABS.map((tab) => {
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
        </View>
      </ScrollView>

      {/* List */}
      {loading && orders.length === 0 ? (
        <View style={styles.listContent}>
          {[1, 2, 3, 4].map((i) => (
            <SkeletonCard key={i} />
          ))}
        </View>
      ) : !loading && orders.length === 0 ? (
        <View style={styles.listContent}>
          <EmptyState
            icon="cart-outline"
            title="No purchase orders"
            description="Create your first purchase order to get started."
          />
        </View>
      ) : (
        <FlatList
          style={styles.list}
          contentContainerStyle={styles.listContent}
          data={orders}
          keyExtractor={(item) => String(item.id)}
          renderItem={({ item }) => (
            <POCard po={item} onPress={() => router.push(`/po/${item.id}`)} />
          )}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.brand[500]} />
          }
          onEndReached={hasMore ? loadMore : undefined}
          onEndReachedThreshold={0.3}
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
  headerRight: {
    flexDirection: 'row',
    gap: 12,
  },

  // KPIs — same as approvals.tsx
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

  // Tabs — same as approvals.tsx
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

  // List
  list: {
    flex: 1,
  },
  listContent: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 24,
  },
});

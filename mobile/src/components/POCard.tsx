import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { colors } from '../utils/colors';
import { fmtAmount, fmtDate } from '../utils/formatters';
import type { PurchaseOrder } from '../types';

interface Props {
  po: PurchaseOrder;
  onPress: () => void;
}

const PO_STATUS_MAP: Record<string, { label: string; color: string; bg: string }> = {
  draft:              { label: 'Draft',    color: colors.neutral[600], bg: colors.neutral[100] },
  open:               { label: 'Open',     color: colors.info[600],    bg: colors.info[50] },
  partially_received: { label: 'Partial',  color: colors.warning[700], bg: colors.warning[50] },
  fully_received:     { label: 'Received', color: colors.success[700], bg: colors.success[50] },
  closed:             { label: 'Closed',   color: colors.neutral[700], bg: colors.neutral[200] },
  cancelled:          { label: 'Cancelled',color: colors.danger[600],  bg: colors.danger[50] },
};

export default function POCard({ po, onPress }: Props) {
  const sc = PO_STATUS_MAP[po.status] || PO_STATUS_MAP.open;

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.7}>
      <View style={styles.topRow}>
        <Text style={styles.poNumber} numberOfLines={1}>{po.po_number}</Text>
        <View style={[styles.badge, { backgroundColor: sc.bg }]}>
          <Text style={[styles.badgeText, { color: sc.color }]}>{sc.label}</Text>
        </View>
      </View>

      <Text style={styles.vendor} numberOfLines={1}>{po.vendor_name}</Text>

      <View style={styles.bottomRow}>
        <Text style={styles.amount}>{po.currency} {fmtAmount(po.total_amount)}</Text>
        <Text style={styles.meta}>{fmtDate(po.po_date)}</Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.neutral[100],
    padding: 16,
    marginBottom: 10,
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  poNumber: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.neutral[900],
    flex: 1,
    marginRight: 8,
  },
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  badgeText: {
    fontSize: 11,
    fontWeight: '700',
  },
  vendor: {
    fontSize: 13,
    color: colors.neutral[600],
    marginBottom: 10,
  },
  bottomRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  amount: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.brand[600],
    fontVariant: ['tabular-nums'],
  },
  meta: {
    fontSize: 12,
    color: colors.neutral[400],
  },
});

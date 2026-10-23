import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { colors } from '../utils/colors';
import { fmtAmount, fmtDate } from '../utils/formatters';
import StatusBadge from './StatusBadge';
import type { InvoiceListItem } from '../types';

interface Props {
  invoice: InvoiceListItem;
  onPress: () => void;
  highlighted?: boolean;
}

export default function InvoiceCard({ invoice, onPress, highlighted }: Props) {
  return (
    <TouchableOpacity
      style={[styles.card, highlighted && styles.cardHighlighted]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <View style={styles.topRow}>
        <View style={styles.numWrap}>
          {highlighted && <View style={styles.newDot} />}
          <Text style={styles.invoiceNum} numberOfLines={1}>
            {invoice.invoice_number || 'No Invoice #'}
          </Text>
        </View>
        <StatusBadge status={invoice.status} />
      </View>

      <Text style={styles.supplier} numberOfLines={1}>
        {invoice.supplier_name || 'Unknown Supplier'}
      </Text>

      <View style={styles.bottomRow}>
        <Text style={styles.amount}>
          {invoice.currency} {fmtAmount(invoice.total_amount)}
        </Text>
        <Text style={styles.date}>{fmtDate(invoice.created_at)}</Text>
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
  cardHighlighted: {
    backgroundColor: colors.success[50],
    borderColor: colors.success[200],
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  numWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flex: 1,
    marginRight: 8,
  },
  newDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.success[500],
  },
  invoiceNum: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.neutral[900],
    flex: 1,
  },
  supplier: {
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
  date: {
    fontSize: 12,
    color: colors.neutral[400],
  },
});

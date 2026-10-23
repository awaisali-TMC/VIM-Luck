import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../utils/colors';
import { fmtAmount } from '../utils/formatters';

interface Props {
  currency: string;
  baseCurrency?: string;
  exchangeRate?: number | null;
  totalAmount?: number | null;
  baseTotalAmount?: number | null;
}

export default function MultiCurrencyCard({
  currency,
  baseCurrency,
  exchangeRate,
  totalAmount,
  baseTotalAmount,
}: Props) {
  // Only show for foreign currency invoices
  if (!baseCurrency || baseCurrency === currency || !exchangeRate) return null;

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Ionicons name="swap-horizontal" size={16} color="#6366F1" />
        <Text style={styles.title}>Multi-Currency</Text>
      </View>

      <View style={styles.conversionRow}>
        <View style={styles.currencyBox}>
          <Text style={styles.currencyCode}>{currency}</Text>
          <Text style={styles.currencyAmount}>{fmtAmount(totalAmount)}</Text>
          <Text style={styles.currencyLabel}>Original</Text>
        </View>

        <View style={styles.arrowBox}>
          <Ionicons name="arrow-forward" size={16} color={colors.neutral[400]} />
          <Text style={styles.rateText}>Rate: {exchangeRate?.toFixed(4)}</Text>
        </View>

        <View style={styles.currencyBox}>
          <Text style={[styles.currencyCode, { color: colors.brand[600] }]}>{baseCurrency}</Text>
          <Text style={[styles.currencyAmount, { color: colors.brand[600] }]}>
            {fmtAmount(baseTotalAmount)}
          </Text>
          <Text style={styles.currencyLabel}>Converted</Text>
        </View>
      </View>
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
  },
  conversionRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  currencyBox: {
    flex: 1,
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    padding: 10,
    alignItems: 'center',
  },
  currencyCode: {
    fontSize: 14,
    fontWeight: '800',
    color: colors.neutral[800],
  },
  currencyAmount: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.neutral[700],
    marginTop: 2,
  },
  currencyLabel: {
    fontSize: 9,
    color: colors.neutral[400],
    marginTop: 2,
    textTransform: 'uppercase',
    fontWeight: '600',
  },
  arrowBox: {
    alignItems: 'center',
    paddingHorizontal: 8,
  },
  rateText: {
    fontSize: 8,
    color: colors.neutral[400],
    fontWeight: '600',
    marginTop: 2,
  },
});

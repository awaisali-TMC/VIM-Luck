import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors } from '../utils/colors';
import { confTier } from '../utils/formatters';

const CONF_COLORS = {
  high: '#10B981',
  medium: '#F59E0B',
  low: '#EF4444',
};

interface Props {
  label: string;
  value: string | number | null | undefined;
  confidence?: number | null;
}

export default function FieldRow({ label, value, confidence }: Props) {
  const tier = confTier(confidence ?? null);

  return (
    <View style={styles.row}>
      <View style={styles.labelRow}>
        {tier && <View style={[styles.confDot, { backgroundColor: CONF_COLORS[tier] }]} />}
        <Text style={styles.label}>{label}</Text>
      </View>
      <Text style={styles.value}>{value ?? '—'}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.neutral[100],
  },
  labelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginBottom: 2,
  },
  confDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  label: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.neutral[500],
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  value: {
    fontSize: 14,
    color: colors.neutral[800],
    fontWeight: '500',
  },
});

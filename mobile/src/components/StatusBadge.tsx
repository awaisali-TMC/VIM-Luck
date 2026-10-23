import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { statusColors } from '../utils/colors';
import { getStatusLabel } from '../services/calculations';

interface Props {
  status: string;
  label?: string;
  size?: 'sm' | 'md';
}

export default function StatusBadge({ status, label: labelOverride, size = 'sm' }: Props) {
  const c = statusColors[status] || statusColors.draft;
  const label = labelOverride || getStatusLabel(status);

  return (
    <View style={[styles.badge, { backgroundColor: c.bg }, size === 'md' && styles.badgeMd]}>
      <View style={[styles.dot, { backgroundColor: c.dot }]} />
      <Text style={[styles.label, { color: c.text }, size === 'md' && styles.labelMd]}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 99,
    gap: 5,
  },
  badgeMd: {
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  label: {
    fontSize: 11,
    fontWeight: '600',
  },
  labelMd: {
    fontSize: 13,
  },
});

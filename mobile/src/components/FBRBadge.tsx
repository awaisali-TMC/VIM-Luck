import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../utils/colors';

interface Props {
  verificationStatus: string | null | undefined;
  taxpayerName?: string | null;
  filingStatus?: string | null;
  whtCompliance?: string | null;
}

const STATUS_CONFIG: Record<string, {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  color: string;
  bg: string;
}> = {
  verified_active: {
    icon: 'shield-checkmark',
    label: 'ATL Active',
    color: colors.success[700],
    bg: colors.success[50],
  },
  verified_inactive: {
    icon: 'shield-half-outline',
    label: 'Non-ATL',
    color: colors.danger[700],
    bg: colors.danger[50],
  },
  verified: {
    icon: 'shield-checkmark',
    label: 'FBR Verified',
    color: colors.success[700],
    bg: colors.success[50],
  },
  not_found: {
    icon: 'help-circle-outline',
    label: 'NTN Not Found',
    color: colors.warning[700],
    bg: colors.warning[50],
  },
  not_verified: {
    icon: 'shield-outline',
    label: 'Not Verified',
    color: colors.neutral[500],
    bg: colors.neutral[100],
  },
  failed: {
    icon: 'close-circle',
    label: 'Verification Failed',
    color: colors.danger[700],
    bg: colors.danger[50],
  },
  pending: {
    icon: 'time-outline',
    label: 'Pending Verification',
    color: colors.info[700],
    bg: colors.info[50],
  },
};

export default function FBRBadge({ verificationStatus, taxpayerName, filingStatus, whtCompliance }: Props) {
  if (!verificationStatus) return null;

  const config = STATUS_CONFIG[verificationStatus] || STATUS_CONFIG.not_verified;

  return (
    <View style={[styles.container, { backgroundColor: config.bg }]}>
      <View style={styles.headerRow}>
        <Ionicons name={config.icon} size={16} color={config.color} />
        <Text style={[styles.statusText, { color: config.color }]}>{config.label}</Text>
      </View>

      {taxpayerName && (
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Taxpayer</Text>
          <Text style={styles.detailValue}>{taxpayerName}</Text>
        </View>
      )}

      {filingStatus && (
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Filing</Text>
          <Text style={[
            styles.detailValue,
            { color: filingStatus.toLowerCase().includes('active') || filingStatus === 'filer'
                ? colors.success[600]
                : colors.warning[600] },
          ]}>
            {filingStatus}
          </Text>
        </View>
      )}

      {whtCompliance && (
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>WHT</Text>
          <Text style={[
            styles.detailValue,
            { color: whtCompliance === 'compliant'
                ? colors.success[600]
                : whtCompliance === 'needs_review'
                  ? colors.warning[600]
                  : colors.danger[600] },
          ]}>
            {whtCompliance === 'compliant' ? 'Compliant'
              : whtCompliance === 'needs_review' ? 'Needs Review'
              : 'Non-Compliant'}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 12,
    padding: 12,
    marginBottom: 12,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 8,
  },
  statusText: {
    fontSize: 13,
    fontWeight: '700',
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 3,
  },
  detailLabel: {
    fontSize: 11,
    color: colors.neutral[500],
    fontWeight: '500',
  },
  detailValue: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.neutral[800],
  },
});

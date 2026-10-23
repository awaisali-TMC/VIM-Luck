import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { colors } from '../utils/colors';
import { checkDuplicates } from '../services/analyticsService';
import { fmtAmount, fmtDate } from '../utils/formatters';

interface Props {
  invoiceId: number;
}

interface Match {
  id: number;
  invoice_number?: string | null;
  supplier_name?: string | null;
  total_amount?: number | null;
  currency?: string | null;
  invoice_date?: string | null;
  match_type?: string;
}

// Severity mirrors the web: exact → red, probable → amber, possible → blue.
type Severity = 'danger' | 'warning' | 'info';
const SEVERITY: Record<Severity, { tint: any; title: string; icon: any }> = {
  danger: { tint: colors.danger, title: 'Exact Duplicate Found', icon: 'alert-circle' },
  warning: { tint: colors.warning, title: 'Probable Duplicate', icon: 'warning' },
  info: { tint: colors.info, title: 'Possible Duplicate', icon: 'information-circle' },
};

export default function DuplicateWarning({ invoiceId }: Props) {
  const router = useRouter();
  const [data, setData] = useState<{ severity: Severity; matches: Match[] } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkDuplicates(invoiceId)
      .then((res: any) => {
        if (!res || !res.has_duplicates) return;
        const exact: Match[] = res.exact_matches || [];
        const probable: Match[] = res.probable_matches || [];
        const possible: Match[] = res.possible_matches || [];
        const severity: Severity = exact.length ? 'danger' : probable.length ? 'warning' : 'info';
        const matches = [...exact, ...probable, ...possible];
        if (matches.length) setData({ severity, matches });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [invoiceId]);

  if (loading || !data) return null;

  const cfg = SEVERITY[data.severity];
  const total = data.matches.length;

  return (
    <View style={[styles.container, { backgroundColor: cfg.tint[50], borderColor: cfg.tint[200] }]}>
      <View style={styles.headerRow}>
        <Ionicons name={cfg.icon} size={18} color={cfg.tint[600]} />
        <Text style={[styles.title, { color: cfg.tint[700] }]}>{cfg.title}</Text>
        <Text style={[styles.count, { color: cfg.tint[600] }]}>
          {total} match{total !== 1 ? 'es' : ''} found
        </Text>
      </View>
      <Text style={[styles.subtitle, { color: cfg.tint[600] }]}>
        {data.severity === 'danger'
          ? 'The same invoice number already exists — review before processing.'
          : 'A similar invoice was detected. Please review before processing.'}
      </Text>

      {data.matches.slice(0, 3).map((dup) => (
        <TouchableOpacity
          key={dup.id}
          style={[styles.dupCard, { borderColor: cfg.tint[200] }]}
          onPress={() => router.push(`/invoice/${dup.id}`)}
        >
          <View style={styles.dupHeader}>
            <Text style={styles.dupInvNum}>#{dup.invoice_number || dup.id}</Text>
            <View style={[styles.matchPill, { backgroundColor: cfg.tint[100] }]}>
              <Text style={[styles.matchText, { color: cfg.tint[700] }]}>{dup.match_type || 'match'}</Text>
            </View>
          </View>
          <Text style={styles.dupMeta}>
            {dup.supplier_name || 'Unknown'} · {dup.currency || ''} {fmtAmount(dup.total_amount)} · {fmtDate(dup.invoice_date)}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    marginBottom: 12,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  title: {
    fontSize: 13,
    fontWeight: '700',
  },
  count: {
    fontSize: 11,
    fontWeight: '600',
    marginLeft: 'auto',
  },
  subtitle: {
    fontSize: 11,
    marginBottom: 10,
  },
  dupCard: {
    backgroundColor: '#fff',
    borderRadius: 8,
    padding: 10,
    marginBottom: 6,
    borderWidth: 1,
  },
  dupHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 3,
  },
  dupInvNum: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.neutral[800],
  },
  matchPill: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
  },
  matchText: {
    fontSize: 10,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  dupMeta: {
    fontSize: 10,
    color: colors.neutral[500],
  },
});

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  TextInput,
  Alert,
  ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../utils/colors';
import { fmtAmount } from '../utils/formatters';
import {
  getInvoiceMatches,
  autoSuggestPO,
  searchPurchaseOrders,
  triggerPOMatch,
} from '../services/purchaseOrderService';
import type { POMatchResult, POSuggestion, PurchaseOrder } from '../types';

interface Props {
  invoiceId: number;
  poReference?: string | null;
}

const STATUS_CONFIG: Record<string, { bg: string; text: string; icon: string }> = {
  full_match:    { bg: colors.success[50], text: colors.success[700], icon: 'checkmark-circle' },
  partial_match: { bg: colors.warning[50], text: colors.warning[700], icon: 'alert-circle' },
  mismatch:      { bg: colors.danger[50],  text: colors.danger[600],  icon: 'close-circle' },
  unmatched:     { bg: colors.neutral[100], text: colors.neutral[600], icon: 'help-circle' },
};

export default function POMatchCard({ invoiceId, poReference }: Props) {
  const [matches, setMatches] = useState<POMatchResult[]>([]);
  const [suggestions, setSuggestions] = useState<POSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [matchRunning, setMatchRunning] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [expandedMatch, setExpandedMatch] = useState<number | null>(null);

  // Search
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<PurchaseOrder[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedPO, setSelectedPO] = useState<number | null>(null);
  const [matchType, setMatchType] = useState<'2-way' | '3-way'>('2-way');

  const loadMatches = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getInvoiceMatches(invoiceId);
      setMatches(data);

      if (data.length === 0 && poReference) {
        try {
          const sugs = await autoSuggestPO(invoiceId);
          setSuggestions(sugs);
        } catch {}
      }
    } catch {}
    finally { setLoading(false); }
  }, [invoiceId, poReference]);

  useEffect(() => { loadMatches(); }, [loadMatches]);

  const handleSearch = async (q: string) => {
    setSearchQuery(q);
    if (q.length < 2) { setSearchResults([]); return; }
    try {
      setSearching(true);
      const results = await searchPurchaseOrders(q);
      setSearchResults(results);
    } catch {}
    finally { setSearching(false); }
  };

  const runMatch = async (poId: number) => {
    try {
      setMatchRunning(true);
      await triggerPOMatch(invoiceId, poId, matchType);
      await loadMatches();
      setSelectedPO(null);
      setSearchQuery('');
      setSearchResults([]);
    } catch (err: any) {
      Alert.alert('Match Error', err.response?.data?.detail || err.message || 'Failed to run match.');
    } finally {
      setMatchRunning(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.card}>
        <View style={styles.header}>
          <Ionicons name="git-compare-outline" size={18} color={colors.brand[500]} />
          <Text style={styles.title}>PO Matching</Text>
        </View>
        <ActivityIndicator size="small" color={colors.brand[500]} style={{ paddingVertical: 12 }} />
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <TouchableOpacity style={styles.header} onPress={() => setExpanded(!expanded)}>
        <View style={styles.headerLeft}>
          <Ionicons name="git-compare-outline" size={18} color={colors.brand[500]} />
          <Text style={styles.title}>PO Matching</Text>
          {matches.length > 0 && (
            <View style={[styles.countBadge, { backgroundColor: colors.brand[100] }]}>
              <Text style={[styles.countText, { color: colors.brand[700] }]}>{matches.length}</Text>
            </View>
          )}
        </View>
        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={18}
          color={colors.neutral[400]}
        />
      </TouchableOpacity>

      {expanded && (
        <View style={styles.body}>
          {/* Suggestions */}
          {suggestions.length > 0 && matches.length === 0 && (
            <View style={styles.suggestSection}>
              <Text style={styles.subLabel}>Suggested POs</Text>
              {suggestions.map((s) => (
                <TouchableOpacity
                  key={s.po_id}
                  style={styles.suggestCard}
                  onPress={() => {
                    setSelectedPO(s.po_id);
                    setSearchQuery(s.po_number);
                    setSearchResults([]);
                  }}
                >
                  <View style={styles.suggestInfo}>
                    <Text style={styles.suggestPO}>{s.po_number}</Text>
                    <Text style={styles.suggestVendor}>{s.vendor_name}</Text>
                  </View>
                  <View style={styles.confPill}>
                    <Text style={styles.confText}>{Math.round(s.confidence * 100)}%</Text>
                  </View>
                </TouchableOpacity>
              ))}
            </View>
          )}

          {/* Manual Search */}
          <View style={styles.searchSection}>
            <Text style={styles.subLabel}>Search PO</Text>
            <TextInput
              style={styles.searchInput}
              value={searchQuery}
              onChangeText={handleSearch}
              placeholder="Type PO number or vendor..."
              placeholderTextColor={colors.neutral[300]}
            />
            {searching && <ActivityIndicator size="small" color={colors.brand[500]} style={{ marginTop: 4 }} />}
            {searchResults.length > 0 && (
              <View style={styles.searchDropdown}>
                {searchResults.slice(0, 5).map((r) => (
                  <TouchableOpacity
                    key={r.id}
                    style={styles.searchItem}
                    onPress={() => {
                      setSelectedPO(r.id);
                      setSearchQuery(r.po_number);
                      setSearchResults([]);
                    }}
                  >
                    <Text style={styles.searchPO}>{r.po_number}</Text>
                    <Text style={styles.searchVendor}>{r.vendor_name}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}
          </View>

          {/* Match Type + Run */}
          {selectedPO && (
            <View style={styles.runSection}>
              <View style={styles.matchTypeRow}>
                <TouchableOpacity
                  style={[styles.matchTypeBtn, matchType === '2-way' && styles.matchTypeBtnActive]}
                  onPress={() => setMatchType('2-way')}
                >
                  <Text style={[styles.matchTypeBtnText, matchType === '2-way' && styles.matchTypeBtnTextActive]}>
                    2-Way
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.matchTypeBtn, matchType === '3-way' && styles.matchTypeBtnActive]}
                  onPress={() => setMatchType('3-way')}
                >
                  <Text style={[styles.matchTypeBtnText, matchType === '3-way' && styles.matchTypeBtnTextActive]}>
                    3-Way
                  </Text>
                </TouchableOpacity>
              </View>
              <TouchableOpacity
                style={styles.runBtn}
                onPress={() => runMatch(selectedPO)}
                disabled={matchRunning}
              >
                {matchRunning ? (
                  <ActivityIndicator size="small" color="#fff" />
                ) : (
                  <>
                    <Ionicons name="play-circle" size={16} color="#fff" />
                    <Text style={styles.runBtnText}>Run Match</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          )}

          {/* Match Results */}
          {matches.map((m) => {
            const sc = STATUS_CONFIG[m.match_status] || STATUS_CONFIG.unmatched;
            const isExpanded = expandedMatch === m.id;
            return (
              <View key={m.id} style={styles.matchCard}>
                <TouchableOpacity
                  style={styles.matchHeader}
                  onPress={() => setExpandedMatch(isExpanded ? null : m.id)}
                >
                  <View style={[styles.matchBadge, { backgroundColor: sc.bg }]}>
                    <Ionicons name={sc.icon as any} size={14} color={sc.text} />
                    <Text style={[styles.matchBadgeText, { color: sc.text }]}>
                      {m.match_status.replace(/_/g, ' ')}
                    </Text>
                  </View>
                  <View style={styles.matchMeta}>
                    <Text style={styles.matchPO}>{m.po_number || `PO #${m.po_id}`}</Text>
                    <Text style={styles.matchScore}>
                      {Math.round((m.overall_score || 0) * 100)}% | {m.match_type}
                    </Text>
                  </View>
                  <Ionicons
                    name={isExpanded ? 'chevron-up' : 'chevron-down'}
                    size={16}
                    color={colors.neutral[400]}
                  />
                </TouchableOpacity>

                {isExpanded && m.line_matches && (
                  <View style={styles.lineMatchList}>
                    {m.line_matches.map((lm, idx) => {
                      const lsc = STATUS_CONFIG[lm.match_status] || STATUS_CONFIG.unmatched;
                      return (
                        <View key={idx} style={styles.lineMatchRow}>
                          <View style={[styles.lineMatchDot, { backgroundColor: lsc.text }]} />
                          <View style={styles.lineMatchInfo}>
                            <Text style={styles.lineMatchDesc} numberOfLines={1}>
                              {lm.invoice_line_description || lm.po_line_description || `Line ${idx + 1}`}
                            </Text>
                            <View style={styles.lineMatchMetaRow}>
                              <Text style={styles.lineMatchMeta}>
                                Qty: {lm.quantity_match ? '✓' : '✗'}
                                {lm.quantity_diff_pct != null ? ` (${lm.quantity_diff_pct.toFixed(1)}%)` : ''}
                              </Text>
                              <Text style={styles.lineMatchMeta}>
                                Price: {lm.price_match ? '✓' : '✗'}
                                {lm.price_diff_pct != null ? ` (${lm.price_diff_pct.toFixed(1)}%)` : ''}
                              </Text>
                              {m.match_type === '3-way' && lm.grn_received_qty != null && (
                                <Text style={styles.lineMatchMeta}>
                                  GRN: {lm.grn_received_qty}
                                </Text>
                              )}
                            </View>
                          </View>
                        </View>
                      );
                    })}
                    {m.total_amount_diff != null && (
                      <View style={styles.diffRow}>
                        <Text style={styles.diffLabel}>Total Diff:</Text>
                        <Text style={styles.diffValue}>
                          {fmtAmount(m.total_amount_diff)}
                          {m.total_amount_diff_pct != null ? ` (${m.total_amount_diff_pct.toFixed(1)}%)` : ''}
                        </Text>
                      </View>
                    )}
                  </View>
                )}
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#fff',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.neutral[100],
    marginBottom: 12,
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 14,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 14, fontWeight: '700', color: colors.neutral[800] },
  countBadge: { paddingHorizontal: 6, paddingVertical: 1, borderRadius: 8 },
  countText: { fontSize: 10, fontWeight: '700' },

  body: { padding: 14, paddingTop: 0 },

  subLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.neutral[500],
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 6,
  },

  suggestSection: { marginBottom: 12 },
  suggestCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    padding: 10,
    marginBottom: 6,
    borderWidth: 1,
    borderColor: colors.neutral[200],
  },
  suggestInfo: { flex: 1 },
  suggestPO: { fontSize: 13, fontWeight: '700', color: colors.brand[600] },
  suggestVendor: { fontSize: 11, color: colors.neutral[500] },
  confPill: {
    backgroundColor: colors.success[50],
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
  },
  confText: { fontSize: 11, fontWeight: '700', color: colors.success[700] },

  searchSection: { marginBottom: 12 },
  searchInput: {
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 13,
    color: colors.neutral[800],
  },
  searchDropdown: {
    backgroundColor: '#fff',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    marginTop: 4,
  },
  searchItem: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[100],
  },
  searchPO: { fontSize: 13, fontWeight: '700', color: colors.brand[600] },
  searchVendor: { fontSize: 11, color: colors.neutral[500] },

  runSection: { marginBottom: 12, gap: 8 },
  matchTypeRow: { flexDirection: 'row', gap: 8 },
  matchTypeBtn: {
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: colors.neutral[100],
    borderWidth: 1,
    borderColor: colors.neutral[200],
  },
  matchTypeBtnActive: { backgroundColor: colors.brand[600], borderColor: colors.brand[600] },
  matchTypeBtnText: { fontSize: 12, fontWeight: '600', color: colors.neutral[600] },
  matchTypeBtnTextActive: { color: '#fff' },

  runBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    backgroundColor: colors.brand[600],
    borderRadius: 10,
  },
  runBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },

  matchCard: {
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    overflow: 'hidden',
  },
  matchHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 10,
    gap: 8,
  },
  matchBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  matchBadgeText: { fontSize: 10, fontWeight: '700', textTransform: 'capitalize' },
  matchMeta: { flex: 1 },
  matchPO: { fontSize: 13, fontWeight: '700', color: colors.neutral[800] },
  matchScore: { fontSize: 11, color: colors.neutral[500] },

  lineMatchList: { padding: 10, paddingTop: 0 },
  lineMatchRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[200],
  },
  lineMatchDot: { width: 6, height: 6, borderRadius: 3, marginTop: 5, marginRight: 8 },
  lineMatchInfo: { flex: 1 },
  lineMatchDesc: { fontSize: 12, fontWeight: '600', color: colors.neutral[700] },
  lineMatchMetaRow: { flexDirection: 'row', gap: 10, marginTop: 2 },
  lineMatchMeta: { fontSize: 10, color: colors.neutral[500] },

  diffRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    marginTop: 4,
  },
  diffLabel: { fontSize: 12, fontWeight: '600', color: colors.neutral[500] },
  diffValue: { fontSize: 12, fontWeight: '700', color: colors.neutral[800], fontVariant: ['tabular-nums'] },
});

import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../utils/colors';
import { classifyInvoice } from '../services/analyticsService';

const TYPE_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  po_material: { label: 'PO — Material', color: '#3B82F6', icon: 'cube' },
  po_service: { label: 'PO — Service', color: '#8B5CF6', icon: 'construct' },
  non_po: { label: 'Non-PO', color: '#F59E0B', icon: 'document' },
  import_invoice: { label: 'Import', color: '#059669', icon: 'globe' },
  credit_note: { label: 'Credit Note', color: '#10B981', icon: 'remove-circle' },
  debit_note: { label: 'Debit Note', color: '#EF4444', icon: 'add-circle' },
  utility: { label: 'Utility', color: '#6366F1', icon: 'flash' },
  expense: { label: 'Expense', color: '#EC4899', icon: 'card' },
};

interface Props {
  invoiceId: number;
  currentDocType?: string | null;
}

export default function ClassificationBadge({ invoiceId, currentDocType }: Props) {
  const [classification, setClassification] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClassify = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await classifyInvoice(invoiceId);
      setClassification(result);
    } catch {
      setError('Classification failed');
    } finally {
      setLoading(false);
    }
  };

  const currentCfg = currentDocType ? TYPE_CONFIG[currentDocType] : null;

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <View style={styles.titleRow}>
          <Ionicons name="sparkles" size={16} color={colors.brand[500]} />
          <Text style={styles.title}>Auto-Classification</Text>
          {currentCfg && (
            <View style={[styles.typePill, { backgroundColor: currentCfg.color + '15' }]}>
              <Text style={[styles.typePillText, { color: currentCfg.color }]}>
                {currentCfg.label}
              </Text>
            </View>
          )}
        </View>
        {!classification && !loading && (
          <TouchableOpacity style={styles.classifyBtn} onPress={handleClassify}>
            <Text style={styles.classifyBtnText}>Classify</Text>
          </TouchableOpacity>
        )}
      </View>

      {loading && (
        <View style={styles.loadingRow}>
          <ActivityIndicator size="small" color={colors.brand[500]} />
          <Text style={styles.loadingText}>Analyzing invoice...</Text>
        </View>
      )}

      {error && (
        <Text style={styles.errorText}>{error}</Text>
      )}

      {classification && (
        <View style={styles.resultSection}>
          {(() => {
            const cfg = TYPE_CONFIG[classification.invoice_type] || TYPE_CONFIG.non_po;
            return (
              <View style={styles.resultCard}>
                <View style={styles.resultHeader}>
                  <Ionicons name={cfg.icon as any} size={20} color={cfg.color} />
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.resultType, { color: cfg.color }]}>{cfg.label}</Text>
                    <Text style={styles.resultConf}>
                      Confidence: {classification.confidence}%
                    </Text>
                  </View>
                  <View style={styles.confBarBg}>
                    <View
                      style={[
                        styles.confBarFill,
                        {
                          width: `${classification.confidence}%`,
                          backgroundColor:
                            classification.confidence >= 70
                              ? colors.success[500]
                              : classification.confidence >= 40
                              ? colors.warning[500]
                              : colors.danger[500],
                        },
                      ]}
                    />
                  </View>
                </View>
                {classification.reasoning && (
                  <Text style={styles.reasoning}>{classification.reasoning}</Text>
                )}
              </View>
            );
          })()}

          <TouchableOpacity style={styles.reclassifyBtn} onPress={handleClassify} disabled={loading}>
            <Ionicons name="refresh" size={14} color={colors.brand[500]} />
            <Text style={styles.reclassifyText}>Re-classify</Text>
          </TouchableOpacity>
        </View>
      )}

      {!classification && !loading && !error && (
        <Text style={styles.hint}>Tap "Classify" to auto-detect invoice type</Text>
      )}
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
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flex: 1,
  },
  title: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.neutral[800],
  },
  typePill: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
    marginLeft: 6,
  },
  typePillText: {
    fontSize: 10,
    fontWeight: '700',
  },
  classifyBtn: {
    backgroundColor: colors.brand[50],
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  classifyBtnText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.brand[600],
  },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 12,
    justifyContent: 'center',
  },
  loadingText: {
    fontSize: 12,
    color: colors.neutral[400],
  },
  errorText: {
    fontSize: 12,
    color: colors.danger[600],
    textAlign: 'center',
    paddingVertical: 8,
  },
  resultSection: {
    gap: 8,
  },
  resultCard: {
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.neutral[100],
  },
  resultHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  resultType: {
    fontSize: 13,
    fontWeight: '700',
  },
  resultConf: {
    fontSize: 10,
    color: colors.neutral[500],
    marginTop: 1,
  },
  confBarBg: {
    width: 50,
    height: 4,
    backgroundColor: colors.neutral[200],
    borderRadius: 2,
    overflow: 'hidden',
  },
  confBarFill: {
    height: 4,
    borderRadius: 2,
  },
  reasoning: {
    fontSize: 11,
    color: colors.neutral[500],
    marginTop: 8,
    lineHeight: 16,
  },
  reclassifyBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: 6,
  },
  reclassifyText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.brand[500],
  },
  hint: {
    fontSize: 11,
    color: colors.neutral[400],
    textAlign: 'center',
    paddingVertical: 4,
  },
});

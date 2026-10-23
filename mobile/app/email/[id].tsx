import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../../src/utils/colors';
import { fmtDate, fmtFileSize } from '../../src/utils/formatters';
import { hapticSuccess, hapticError } from '../../src/utils/haptics';
import { getEmail, processAttachment } from '../../src/services/emailService';
import SectionCard from '../../src/components/SectionCard';
import FieldRow from '../../src/components/FieldRow';
import { SkeletonCard } from '../../src/components/SkeletonLoader';
import type { EmailMessage, EmailAttachment } from '../../src/types';

const MIME_ICONS: Record<string, { icon: string; color: string; bg: string }> = {
  'application/pdf': { icon: 'document', color: '#DC2626', bg: '#FEE2E2' },
  'image/jpeg':      { icon: 'image', color: '#D97706', bg: '#FEF3C7' },
  'image/png':       { icon: 'image', color: '#2563EB', bg: '#DBEAFE' },
  'image/tiff':      { icon: 'image', color: '#7C3AED', bg: '#EDE9FE' },
};

export default function EmailDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const emailId = parseInt(id!, 10);

  const [email, setEmail] = useState<EmailMessage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [processingId, setProcessingId] = useState<number | null>(null);

  const loadEmail = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getEmail(emailId);
      setEmail(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load email.');
    } finally {
      setLoading(false);
    }
  }, [emailId]);

  useEffect(() => { loadEmail(); }, [loadEmail]);

  const handleProcessAttachment = async (att: EmailAttachment) => {
    if (att.processed) {
      Alert.alert('Already Processed', `This attachment is linked to Invoice #${att.invoice_id || 'unknown'}.`);
      return;
    }
    try {
      setProcessingId(att.id);
      const result = await processAttachment(att.id);
      hapticSuccess();
      Alert.alert(
        'Processing Complete',
        `Extracted ${result.fields?.length || 0} fields and ${result.line_items?.length || 0} line items.`,
        [
          { text: 'View Results', onPress: () => {
            router.push({
              pathname: '/extraction-results',
              params: {
                result: JSON.stringify(result),
                filename: att.filename,
                fileSize: String(att.file_size),
              },
            });
          }},
          { text: 'OK' },
        ],
      );
      await loadEmail(); // Refresh
    } catch (err: any) {
      hapticError();
      Alert.alert('Error', err.response?.data?.detail || err.message || 'Failed to process attachment.');
    } finally {
      setProcessingId(null);
    }
  };

  if (loading) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {[1, 2, 3].map((i) => <SkeletonCard key={i} />)}
      </ScrollView>
    );
  }

  if (error || !email) {
    return (
      <View style={styles.center}>
        <Ionicons name="alert-circle-outline" size={48} color={colors.danger[400]} />
        <Text style={styles.errorText}>{error || 'Email not found.'}</Text>
        <TouchableOpacity style={styles.backBtn} onPress={() => router.back()}>
          <Text style={styles.backBtnText}>Go Back</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const attachments = email.attachments || [];

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.statusRow}>
          <View style={[styles.statusPill, { backgroundColor: email.status === 'processed' ? colors.success[50] : email.status === 'unread' ? colors.brand[50] : colors.neutral[100] }]}>
            <Text style={[styles.statusText, { color: email.status === 'processed' ? colors.success[700] : email.status === 'unread' ? colors.brand[700] : colors.neutral[600] }]}>
              {email.status.charAt(0).toUpperCase() + email.status.slice(1)}
            </Text>
          </View>
        </View>
        <Text style={styles.subject}>{email.subject || '(no subject)'}</Text>
        <Text style={styles.from}>{email.from_address}</Text>
        <Text style={styles.date}>{fmtDate(email.received_at)}</Text>
      </View>

      {/* Metadata */}
      <SectionCard title="Email Details" defaultOpen>
        <FieldRow label="From" value={email.from_address} />
        <FieldRow label="Subject" value={email.subject || '(no subject)'} />
        <FieldRow label="Received" value={fmtDate(email.received_at)} />
        <FieldRow label="Status" value={email.status} />
        <FieldRow label="UID" value={email.message_uid} />
      </SectionCard>

      {/* Body */}
      {email.body_text && (
        <SectionCard title="Message Body">
          <Text style={styles.bodyText} selectable>
            {email.body_text.slice(0, 2000)}
            {email.body_text.length > 2000 ? '\n\n... (truncated)' : ''}
          </Text>
        </SectionCard>
      )}

      {/* Attachments */}
      <SectionCard title={`Attachments (${attachments.length})`} defaultOpen>
        {attachments.length === 0 ? (
          <Text style={styles.emptyText}>No attachments.</Text>
        ) : (
          attachments.map((att) => {
            const mime = MIME_ICONS[att.content_type] || MIME_ICONS['application/pdf'];
            const isProcessing = processingId === att.id;
            return (
              <View key={att.id} style={styles.attachCard}>
                <View style={styles.attachRow}>
                  <View style={[styles.mimeIcon, { backgroundColor: mime.bg }]}>
                    <Ionicons name={mime.icon as any} size={18} color={mime.color} />
                  </View>
                  <View style={styles.attachInfo}>
                    <Text style={styles.attachName} numberOfLines={1}>{att.filename}</Text>
                    <Text style={styles.attachMeta}>
                      {att.content_type.split('/')[1]?.toUpperCase()} {att.file_size ? `| ${fmtFileSize(att.file_size)}` : ''}
                    </Text>
                  </View>
                </View>

                {att.processed ? (
                  <View style={styles.processedBadge}>
                    <Ionicons name="checkmark-circle" size={14} color={colors.success[600]} />
                    <Text style={styles.processedText}>
                      Processed{att.invoice_id ? ` (Inv #${att.invoice_id})` : ''}
                    </Text>
                  </View>
                ) : (
                  <TouchableOpacity
                    style={styles.processBtn}
                    onPress={() => handleProcessAttachment(att)}
                    disabled={isProcessing}
                  >
                    {isProcessing ? (
                      <ActivityIndicator size="small" color="#fff" />
                    ) : (
                      <>
                        <Ionicons name="scan" size={14} color="#fff" />
                        <Text style={styles.processBtnText}>Process as Invoice</Text>
                      </>
                    )}
                  </TouchableOpacity>
                )}
              </View>
            );
          })
        )}
      </SectionCard>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.neutral[50] },
  content: { padding: 16 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 32 },
  errorText: { fontSize: 15, color: colors.neutral[500], marginTop: 12, marginBottom: 16 },
  backBtn: { paddingHorizontal: 20, paddingVertical: 10, backgroundColor: colors.brand[600], borderRadius: 8 },
  backBtnText: { color: '#fff', fontWeight: '600' },

  header: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: colors.neutral[100],
  },
  statusRow: { marginBottom: 8 },
  statusPill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, alignSelf: 'flex-start' },
  statusText: { fontSize: 10, fontWeight: '700' },
  subject: { fontSize: 18, fontWeight: '700', color: colors.neutral[900], marginBottom: 4 },
  from: { fontSize: 13, color: colors.neutral[600] },
  date: { fontSize: 12, color: colors.neutral[400], marginTop: 2 },

  bodyText: {
    fontSize: 13,
    lineHeight: 20,
    color: colors.neutral[700],
  },

  emptyText: { fontSize: 13, color: colors.neutral[400], textAlign: 'center', paddingVertical: 12 },

  attachCard: {
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: colors.neutral[200],
  },
  attachRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  mimeIcon: {
    width: 36,
    height: 36,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  attachInfo: { flex: 1 },
  attachName: { fontSize: 13, fontWeight: '600', color: colors.neutral[800] },
  attachMeta: { fontSize: 11, color: colors.neutral[500], marginTop: 1 },

  processedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 8,
    paddingVertical: 6,
    paddingHorizontal: 10,
    backgroundColor: colors.success[50],
    borderRadius: 8,
  },
  processedText: { fontSize: 12, fontWeight: '600', color: colors.success[700] },

  processBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginTop: 8,
    paddingVertical: 9,
    backgroundColor: colors.brand[600],
    borderRadius: 8,
  },
  processBtnText: { fontSize: 13, fontWeight: '700', color: '#fff' },
});

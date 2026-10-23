import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../utils/colors';
import {
  getInvoiceApproval,
  performApprovalAction,
  type ApprovalRequest,
} from '../services/workflowService';
import { getStoredUser } from '../services/authService';

interface Props {
  invoiceId: number;
  invoiceStatus: string;
  onStatusChange?: () => void;
}

const ACTION_COLORS = {
  approved: colors.success[600],
  rejected: colors.danger[600],
  returned: colors.warning[600],
  delegated: colors.info[600],
  skipped: colors.neutral[400],
  pending: colors.neutral[300],
};

export default function ApprovalProgressCard({ invoiceId, invoiceStatus, onStatusChange }: Props) {
  const [approval, setApproval] = useState<ApprovalRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [comments, setComments] = useState('');
  const [acting, setActing] = useState(false);
  const [userRole, setUserRole] = useState('');

  useEffect(() => {
    loadApproval();
    getStoredUser().then((u) => {
      if (u) setUserRole(u.role);
    });
  }, [invoiceId]);

  const loadApproval = async () => {
    try {
      const data = await getInvoiceApproval(invoiceId);
      setApproval(data);
    } catch {
      setApproval(null);
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (action: 'approved' | 'rejected' | 'returned') => {
    if (!approval) return;
    const labels = { approved: 'Approve', rejected: 'Reject', returned: 'Return for Rework' };
    Alert.alert('Confirm', `${labels[action]} this invoice?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: labels[action],
        style: action === 'rejected' ? 'destructive' : 'default',
        onPress: async () => {
          setActing(true);
          try {
            await performApprovalAction(approval.id, action, comments);
            setComments('');
            await loadApproval();
            onStatusChange?.();
          } catch (err: any) {
            Alert.alert('Error', err?.response?.data?.detail || 'Action failed');
          } finally {
            setActing(false);
          }
        },
      },
    ]);
  };

  // Only show for invoices in approval-related statuses
  if (!['pending_approval', 'approved', 'rejected'].includes(invoiceStatus) && !approval) {
    if (!loading) return null;
  }

  if (loading) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="small" color={colors.brand[500]} />
      </View>
    );
  }

  if (!approval) return null;

  const steps = approval.steps || [];
  const actions = approval.actions || [];

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Ionicons name="git-branch" size={16} color={colors.brand[500]} />
        <Text style={styles.title}>Approval Workflow</Text>
        <View style={[
          styles.statusPill,
          {
            backgroundColor:
              approval.overall_status === 'approved' ? colors.success[50] :
              approval.overall_status === 'rejected' ? colors.danger[50] :
              colors.info[50],
          },
        ]}>
          <Text style={[
            styles.statusPillText,
            {
              color:
                approval.overall_status === 'approved' ? colors.success[700] :
                approval.overall_status === 'rejected' ? colors.danger[700] :
                colors.info[700],
            },
          ]}>
            {approval.overall_status}
          </Text>
        </View>
      </View>

      {/* Step Progress */}
      {steps.length > 0 && (
        <View style={styles.stepsRow}>
          {steps.map((step, i) => {
            const actionForStep = actions.find((a) => a.step_order === step.step_order);
            const isCurrent = step.step_order === approval.current_step_order && approval.overall_status === 'in_progress';
            const isCompleted = actionForStep?.action === 'approved' || actionForStep?.action === 'skipped';
            const isRejected = actionForStep?.action === 'rejected';

            let dotColor = colors.neutral[200];
            if (isCompleted) dotColor = colors.success[500];
            else if (isRejected) dotColor = colors.danger[500];
            else if (isCurrent) dotColor = colors.brand[500];

            return (
              <View key={step.step_order} style={styles.stepItem}>
                <View style={[styles.stepDot, { backgroundColor: dotColor }]}>
                  {isCompleted && <Ionicons name="checkmark" size={10} color="#fff" />}
                  {isRejected && <Ionicons name="close" size={10} color="#fff" />}
                  {isCurrent && <View style={styles.stepDotPulse} />}
                </View>
                <Text style={[
                  styles.stepName,
                  { color: isCurrent ? colors.brand[600] : isCompleted ? colors.success[600] : colors.neutral[500] },
                ]} numberOfLines={2}>
                  {step.step_name}
                </Text>
                {actionForStep && (
                  <Text style={styles.stepActor}>{actionForStep.approver_name}</Text>
                )}
                {i < steps.length - 1 && (
                  <View style={[styles.stepLine, { backgroundColor: isCompleted ? colors.success[300] : colors.neutral[200] }]} />
                )}
              </View>
            );
          })}
        </View>
      )}

      {/* Action History */}
      {actions.length > 0 && (
        <View style={styles.historySection}>
          <Text style={styles.historyTitle}>Action History</Text>
          {actions.map((a) => (
            <View key={a.id} style={styles.historyItem}>
              <View style={[styles.historyDot, { backgroundColor: ACTION_COLORS[a.action as keyof typeof ACTION_COLORS] || colors.neutral[300] }]} />
              <View style={{ flex: 1 }}>
                <Text style={styles.historyText}>
                  <Text style={styles.historyBold}>{a.approver_name}</Text>
                  {' '}{a.action} step "{a.step_name}"
                </Text>
                {a.comments && <Text style={styles.historyComment}>{a.comments}</Text>}
                <Text style={styles.historyTime}>
                  {new Date(a.acted_at).toLocaleString()}
                </Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* Action Buttons — show only if in_progress and user can act */}
      {approval.overall_status === 'in_progress' && (
        <View style={styles.actionSection}>
          <TextInput
            style={styles.commentInput}
            placeholder="Add comments (optional)..."
            placeholderTextColor={colors.neutral[400]}
            value={comments}
            onChangeText={setComments}
            multiline
          />
          <View style={styles.actionButtons}>
            <TouchableOpacity
              style={[styles.actionBtn, styles.approveBtn]}
              onPress={() => handleAction('approved')}
              disabled={acting}
            >
              {acting ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <>
                  <Ionicons name="checkmark-circle" size={16} color="#fff" />
                  <Text style={styles.actionBtnTextWhite}>Approve</Text>
                </>
              )}
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.actionBtn, styles.rejectBtn]}
              onPress={() => handleAction('rejected')}
              disabled={acting}
            >
              <Ionicons name="close-circle" size={16} color={colors.danger[600]} />
              <Text style={[styles.actionBtnText, { color: colors.danger[600] }]}>Reject</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.actionBtn, styles.returnBtn]}
              onPress={() => handleAction('returned')}
              disabled={acting}
            >
              <Ionicons name="return-down-back" size={16} color={colors.warning[600]} />
              <Text style={[styles.actionBtnText, { color: colors.warning[600] }]}>Return</Text>
            </TouchableOpacity>
          </View>
        </View>
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
    alignItems: 'center',
    gap: 6,
    marginBottom: 12,
  },
  title: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.neutral[800],
    flex: 1,
  },
  statusPill: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
  },
  statusPillText: {
    fontSize: 10,
    fontWeight: '700',
    textTransform: 'capitalize',
  },

  // Steps
  stepsRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[100],
    marginBottom: 10,
  },
  stepItem: {
    flex: 1,
    alignItems: 'center',
    position: 'relative',
  },
  stepDot: {
    width: 22,
    height: 22,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepDotPulse: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#fff',
  },
  stepName: {
    fontSize: 9,
    fontWeight: '600',
    textAlign: 'center',
    marginTop: 4,
    lineHeight: 12,
  },
  stepActor: {
    fontSize: 8,
    color: colors.neutral[400],
    textAlign: 'center',
    marginTop: 1,
  },
  stepLine: {
    position: 'absolute',
    top: 11,
    left: 22,
    right: -10,
    height: 2,
    zIndex: -1,
  },

  // History
  historySection: {
    marginBottom: 10,
  },
  historyTitle: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.neutral[500],
    textTransform: 'uppercase',
    marginBottom: 6,
  },
  historyItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    marginBottom: 8,
  },
  historyDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginTop: 4,
  },
  historyText: {
    fontSize: 11,
    color: colors.neutral[600],
    lineHeight: 16,
  },
  historyBold: {
    fontWeight: '700',
    color: colors.neutral[800],
  },
  historyComment: {
    fontSize: 10,
    color: colors.neutral[500],
    fontStyle: 'italic',
    marginTop: 2,
  },
  historyTime: {
    fontSize: 9,
    color: colors.neutral[400],
    marginTop: 2,
  },

  // Actions
  actionSection: {
    borderTopWidth: 1,
    borderTopColor: colors.neutral[100],
    paddingTop: 12,
  },
  commentInput: {
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 12,
    color: colors.neutral[800],
    minHeight: 40,
    marginBottom: 10,
  },
  actionButtons: {
    flexDirection: 'row',
    gap: 8,
  },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: 10,
    borderRadius: 10,
    borderWidth: 1,
  },
  approveBtn: {
    backgroundColor: colors.success[600],
    borderColor: colors.success[600],
  },
  rejectBtn: {
    backgroundColor: '#fff',
    borderColor: colors.danger[300],
  },
  returnBtn: {
    backgroundColor: '#fff',
    borderColor: colors.warning[300],
  },
  actionBtnText: {
    fontSize: 12,
    fontWeight: '600',
  },
  actionBtnTextWhite: {
    fontSize: 12,
    fontWeight: '600',
    color: '#fff',
  },
});

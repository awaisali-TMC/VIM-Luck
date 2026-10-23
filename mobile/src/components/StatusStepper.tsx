import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../utils/colors';

const STEPS = [
  { key: 'draft', label: 'Received' },
  { key: 'pending_processing', label: 'Validated' },
  { key: 'validated', label: 'Pending Approval' },
  { key: 'approved', label: 'Approved' },
  { key: 'posted', label: 'ERP Posting' },
];

const STATUS_TO_INDEX: Record<string, number> = {
  draft: 0,
  pending_processing: 1,
  validated: 2,
  pending_approval: 2,
  approved: 3,
  posted: 4,
  rejected: 2, // rejected highlights at Pending Approval step
  exception: 2,
};

interface Props {
  currentStatus: string;
}

export default function StatusStepper({ currentStatus }: Props) {
  const currentIdx = STATUS_TO_INDEX[currentStatus] ?? 0;
  const isException = currentStatus === 'exception';
  const isRejected = currentStatus === 'rejected';

  return (
    <View style={styles.container}>
      {STEPS.map((step, i) => {
        const isCompleted = i < currentIdx;
        const isCurrent = i === currentIdx;
        const isExceptionStep = isException && i === 1;
        const isRejectedStep = isRejected && i === 3;

        let circleColor = colors.neutral[200];
        let textColor = colors.neutral[400];
        if (isCompleted) {
          circleColor = colors.success.base;
          textColor = colors.success.dark;
        } else if (isCurrent && (isExceptionStep || isRejectedStep)) {
          circleColor = colors.danger.base;
          textColor = colors.danger.dark;
        } else if (isCurrent) {
          circleColor = colors.brand[500];
          textColor = colors.brand[600];
        }

        return (
          <React.Fragment key={step.key}>
            {i > 0 && (
              <View style={[styles.line, { backgroundColor: isCompleted ? colors.success.base : colors.neutral[200] }]} />
            )}
            <View style={styles.step}>
              <View style={[styles.circle, { backgroundColor: circleColor }]}>
                {isCompleted ? (
                  <Ionicons name="checkmark" size={12} color="#fff" />
                ) : (
                  <Text style={styles.circleText}>{i + 1}</Text>
                )}
              </View>
              <Text style={[styles.stepLabel, { color: textColor }]} numberOfLines={1}>
                {isExceptionStep ? 'Exception' : isRejectedStep ? 'Rejected' : step.label}
              </Text>
            </View>
          </React.Fragment>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 4,
  },
  step: {
    alignItems: 'center',
    width: 52,
  },
  circle: {
    width: 26,
    height: 26,
    borderRadius: 13,
    justifyContent: 'center',
    alignItems: 'center',
  },
  circleText: {
    fontSize: 11,
    fontWeight: '700',
    color: '#fff',
  },
  stepLabel: {
    fontSize: 10,
    fontWeight: '600',
    marginTop: 4,
    textAlign: 'center',
  },
  line: {
    flex: 1,
    height: 2,
    borderRadius: 1,
    marginBottom: 18,
  },
});

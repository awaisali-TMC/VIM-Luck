import React, { useEffect, useRef } from 'react';
import { View, Animated, StyleSheet } from 'react-native';
import { colors } from '../utils/colors';

interface Props {
  width?: number | string;
  height?: number;
  borderRadius?: number;
  style?: any;
}

export default function SkeletonLoader({ width = '100%', height = 16, borderRadius = 6, style }: Props) {
  const opacity = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 1, duration: 600, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.3, duration: 600, useNativeDriver: true }),
      ])
    );
    animation.start();
    return () => animation.stop();
  }, [opacity]);

  return (
    <Animated.View
      style={[
        { width: width as any, height, borderRadius, backgroundColor: colors.neutral[200], opacity },
        style,
      ]}
    />
  );
}

export function SkeletonCard() {
  return (
    <View style={skStyles.card}>
      <View style={skStyles.row}>
        <SkeletonLoader width="60%" height={14} />
        <SkeletonLoader width={70} height={22} borderRadius={11} />
      </View>
      <SkeletonLoader width="40%" height={12} style={{ marginTop: 8 }} />
      <View style={[skStyles.row, { marginTop: 12 }]}>
        <SkeletonLoader width="35%" height={18} />
        <SkeletonLoader width={80} height={12} />
      </View>
    </View>
  );
}

const skStyles = StyleSheet.create({
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.neutral[100],
    padding: 16,
    marginBottom: 10,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
});

import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Animated,
  Dimensions,
  Alert,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { colors } from '../src/utils/colors';
import { logoutInternal, getStoredUser, type InternalUser } from '../src/services/authService';
import { getAnalyticsOverview, type AnalyticsOverview } from '../src/services/analyticsService';
import { fmtAmount } from '../src/utils/formatters';

const { width } = Dimensions.get('window');

interface QuickAction {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  description: string;
  route: string;
  color: string;
  bgColor: string;
}

const QUICK_ACTIONS: QuickAction[] = [
  {
    icon: 'document-text-outline',
    label: 'Invoices',
    description: 'View & manage',
    route: '/(tabs)/invoices',
    color: colors.brand[600],
    bgColor: colors.brand[50],
  },
  {
    icon: 'cart-outline',
    label: 'POs',
    description: 'Purchase orders',
    route: '/purchase-orders',
    color: '#0891B2',
    bgColor: '#ECFEFF',
  },
  {
    icon: 'checkmark-done-circle-outline',
    label: 'Approvals',
    description: 'Status tracker',
    route: '/(tabs)/approvals',
    color: '#8B5CF6',
    bgColor: '#EDE9FE',
  },
  {
    icon: 'mail-outline',
    label: 'Inbox',
    description: 'Email invoices',
    route: '/inbox',
    color: '#EA580C',
    bgColor: '#FFF7ED',
  },
  {
    icon: 'cloud-upload-outline',
    label: 'Upload',
    description: 'Scan or upload',
    route: '/(tabs)/upload',
    color: colors.success[600],
    bgColor: colors.success[50],
  },
  {
    icon: 'settings-outline',
    label: 'Settings',
    description: 'Configuration',
    route: '/(tabs)/settings',
    color: colors.neutral[600],
    bgColor: colors.neutral[50],
  },
];

export default function HomeScreen() {
  const router = useRouter();
  const [userName, setUserName] = useState('');
  const [userRole, setUserRole] = useState('');
  const [greeting, setGreeting] = useState('');
  const [analytics, setAnalytics] = useState<AnalyticsOverview | null>(null);
  const [loadingAnalytics, setLoadingAnalytics] = useState(true);

  // Animations
  const headerOpacity = useRef(new Animated.Value(0)).current;
  const headerTranslateY = useRef(new Animated.Value(-20)).current;
  const cameraScale = useRef(new Animated.Value(0)).current;
  const actionsOpacity = useRef(new Animated.Value(0)).current;
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    // Load user info
    getStoredUser().then((user) => {
      if (user) {
        setUserName(user.display_name || user.email.split('@')[0]);
        setUserRole(user.role?.replace(/_/g, ' ') || '');
      } else {
        AsyncStorage.getItem('user_name').then((name) => {
          setUserName(name || 'User');
        });
      }
    });

    // Load analytics
    getAnalyticsOverview(30)
      .then((data) => setAnalytics(data))
      .catch(() => setAnalytics(null))
      .finally(() => setLoadingAnalytics(false));

    const hour = new Date().getHours();
    if (hour < 12) setGreeting('Good morning');
    else if (hour < 17) setGreeting('Good afternoon');
    else setGreeting('Good evening');

    Animated.stagger(200, [
      Animated.parallel([
        Animated.timing(headerOpacity, { toValue: 1, duration: 500, useNativeDriver: true }),
        Animated.timing(headerTranslateY, { toValue: 0, duration: 500, useNativeDriver: true }),
      ]),
      Animated.spring(cameraScale, { toValue: 1, tension: 50, friction: 7, useNativeDriver: true }),
      Animated.timing(actionsOpacity, { toValue: 1, duration: 400, useNativeDriver: true }),
    ]).start();

    const pulse = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1.08, duration: 1500, useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 1, duration: 1500, useNativeDriver: true }),
      ])
    );
    pulse.start();

    return () => pulse.stop();
  }, []);

  const handleCamera = () => {
    router.push('/scanner');
  };

  const handleLogout = () => {
    Alert.alert('Sign Out', 'Are you sure you want to sign out?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Sign Out',
        style: 'destructive',
        onPress: async () => {
          await logoutInternal();
          router.replace('/login');
        },
      },
    ]);
  };

  return (
    <View style={styles.container}>
      {/* Background */}
      <View style={styles.bgGradient} />
      <View style={styles.bgCircle1} />
      <View style={styles.bgCircle2} />

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <Animated.View
          style={[
            styles.header,
            { opacity: headerOpacity, transform: [{ translateY: headerTranslateY }] },
          ]}
        >
          <View>
            <Text style={styles.greeting}>{greeting},</Text>
            <Text style={styles.userName}>{userName}</Text>
            {userRole ? (
              <View style={styles.rolePill}>
                <Ionicons name="shield-checkmark" size={10} color={colors.brand[300]} />
                <Text style={styles.roleText}>{userRole}</Text>
              </View>
            ) : null}
          </View>
          <TouchableOpacity style={styles.avatarBtn} onPress={handleLogout}>
            <Ionicons name="person-circle-outline" size={38} color="rgba(255,255,255,0.8)" />
          </TouchableOpacity>
        </Animated.View>

        {/* Brand Pill */}
        <View style={styles.brandPill}>
          <View style={styles.brandPillAccent} />
          <Text style={styles.brandPillText}>TMC <Text style={styles.brandPillBold}>eInvoice</Text></Text>
        </View>

        {/* Analytics KPIs */}
        {!loadingAnalytics && analytics && (
          <Animated.View style={[styles.kpiSection, { opacity: actionsOpacity }]}>
            <Text style={styles.kpiSectionTitle}>Overview (30 days)</Text>
            {/* Row 1 — Primary counts */}
            <View style={styles.kpiGrid}>
              <TouchableOpacity style={styles.kpiCard} onPress={() => router.push('/(tabs)/invoices')} activeOpacity={0.7}>
                <Ionicons name="document-text" size={18} color={colors.brand[400]} />
                <Text style={styles.kpiValue}>{analytics.total_invoices}</Text>
                <Text style={styles.kpiLabel}>Total</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.kpiCard} onPress={() => router.push({ pathname: '/(tabs)/invoices', params: { status: 'pending_processing' } })} activeOpacity={0.7}>
                <Ionicons name="hourglass" size={18} color={colors.warning[500]} />
                <Text style={styles.kpiValue}>{analytics.pending_count}</Text>
                <Text style={styles.kpiLabel}>Pending</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.kpiCard} onPress={() => router.push({ pathname: '/(tabs)/invoices', params: { status: 'approved' } })} activeOpacity={0.7}>
                <Ionicons name="checkmark-circle" size={18} color={colors.success[500]} />
                <Text style={styles.kpiValue}>{analytics.approved_count}</Text>
                <Text style={styles.kpiLabel}>Approved</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.kpiCard} onPress={() => router.push({ pathname: '/(tabs)/invoices', params: { status: 'posted' } })} activeOpacity={0.7}>
                <Ionicons name="paper-plane" size={18} color="#60A5FA" />
                <Text style={styles.kpiValue}>{analytics.posted_count}</Text>
                <Text style={styles.kpiLabel}>Posted</Text>
              </TouchableOpacity>
            </View>
            {/* Row 2 — Secondary counts */}
            <View style={[styles.kpiGrid, { marginTop: 8 }]}>
              <TouchableOpacity style={styles.kpiCard} onPress={() => router.push({ pathname: '/(tabs)/invoices', params: { status: 'draft' } })} activeOpacity={0.7}>
                <Ionicons name="create" size={18} color={colors.neutral[400]} />
                <Text style={styles.kpiValue}>{analytics.draft_count}</Text>
                <Text style={styles.kpiLabel}>Draft</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.kpiCard} onPress={() => router.push({ pathname: '/(tabs)/invoices', params: { status: 'validated' } })} activeOpacity={0.7}>
                <Ionicons name="shield-checkmark" size={18} color="#818CF8" />
                <Text style={styles.kpiValue}>{analytics.validated_count}</Text>
                <Text style={styles.kpiLabel}>Validated</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.kpiCard} onPress={() => router.push({ pathname: '/(tabs)/invoices', params: { status: 'exception' } })} activeOpacity={0.7}>
                <Ionicons name="alert-circle" size={18} color={colors.danger[500]} />
                <Text style={styles.kpiValue}>{analytics.exception_count}</Text>
                <Text style={styles.kpiLabel}>Exception</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.kpiCard} onPress={() => router.push({ pathname: '/(tabs)/invoices', params: { status: 'rejected' } })} activeOpacity={0.7}>
                <Ionicons name="close-circle" size={18} color="#F87171" />
                <Text style={styles.kpiValue}>{analytics.rejected_count}</Text>
                <Text style={styles.kpiLabel}>Rejected</Text>
              </TouchableOpacity>
            </View>
            {/* Total Amount + Rates */}
            {analytics.total_amount > 0 && (
              <View style={styles.totalAmountBar}>
                <Text style={styles.totalAmountLabel}>Total Amount</Text>
                <Text style={styles.totalAmountValue}>
                  PKR {fmtAmount(analytics.total_amount)}
                </Text>
              </View>
            )}
            <View style={styles.ratesRow}>
              <View style={styles.rateChip}>
                <Text style={styles.rateValue}>{analytics.avg_confidence.toFixed(0)}%</Text>
                <Text style={styles.rateLabel}>Confidence</Text>
              </View>
              <View style={styles.rateChip}>
                <Text style={styles.rateValue}>{analytics.straight_through_rate.toFixed(0)}%</Text>
                <Text style={styles.rateLabel}>STP Rate</Text>
              </View>
              <View style={styles.rateChip}>
                <Text style={[styles.rateValue, analytics.exception_rate > 10 && { color: '#F87171' }]}>
                  {analytics.exception_rate.toFixed(0)}%
                </Text>
                <Text style={styles.rateLabel}>Exception</Text>
              </View>
            </View>
          </Animated.View>
        )}

        {loadingAnalytics && (
          <View style={styles.kpiLoading}>
            <ActivityIndicator size="small" color={colors.brand[400]} />
          </View>
        )}

        {/* Camera Hero Section */}
        <Animated.View style={[styles.heroSection, { transform: [{ scale: cameraScale }] }]}>
          <Text style={styles.heroTitle}>Scan an Invoice</Text>
          <Text style={styles.heroSubtitle}>
            Capture or upload an invoice to extract data instantly with AI
          </Text>

          <View style={styles.cameraWrapper}>
            <Animated.View
              style={[styles.cameraRingOuter, { transform: [{ scale: pulseAnim }] }]}
            />
            <TouchableOpacity
              style={styles.cameraBtn}
              onPress={handleCamera}
              activeOpacity={0.85}
            >
              <View style={styles.cameraBtnInner}>
                <Ionicons name="camera" size={40} color="#fff" />
              </View>
            </TouchableOpacity>
          </View>

          <Text style={styles.cameraTip}>Tap to start scanning</Text>
        </Animated.View>

        {/* Quick Actions */}
        <Animated.View style={[styles.actionsSection, { opacity: actionsOpacity }]}>
          <Text style={styles.actionsTitle}>Quick Actions</Text>
          <View style={styles.actionsGrid}>
            {QUICK_ACTIONS.map((action) => (
              <TouchableOpacity
                key={action.label}
                style={styles.actionCard}
                onPress={() => router.push(action.route as any)}
                activeOpacity={0.75}
              >
                <View style={[styles.actionIcon, { backgroundColor: action.color + '18' }]}>
                  <Ionicons name={action.icon} size={20} color={action.color} />
                </View>
                <Text style={styles.actionLabel}>{action.label}</Text>
                <Text style={styles.actionDesc}>{action.description}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </Animated.View>

        {/* Stats Preview */}
        <Animated.View style={[styles.statsSection, { opacity: actionsOpacity }]}>
          <View style={styles.statsCard}>
            <View style={styles.statsRow}>
              <View style={styles.statItem}>
                <Ionicons name="shield-checkmark" size={20} color={colors.brand[400]} />
                <Text style={styles.statLabel}>Compliance</Text>
              </View>
              <View style={styles.statDivider} />
              <View style={styles.statItem}>
                <Ionicons name="checkmark-circle" size={20} color={colors.success[500]} />
                <Text style={styles.statLabel}>Automated</Text>
              </View>
              <View style={styles.statDivider} />
              <View style={styles.statItem}>
                <Ionicons name="flash" size={20} color={colors.warning[500]} />
                <Text style={styles.statLabel}>AI Powered</Text>
              </View>
            </View>
          </View>
        </Animated.View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
  bgGradient: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: '55%',
    backgroundColor: '#0A1628',
  },
  bgCircle1: {
    position: 'absolute',
    top: -40,
    right: -60,
    width: 200,
    height: 200,
    borderRadius: 100,
    backgroundColor: colors.brand[400],
    opacity: 0.08,
  },
  bgCircle2: {
    position: 'absolute',
    top: 120,
    left: -40,
    width: 140,
    height: 140,
    borderRadius: 70,
    backgroundColor: colors.brand[600],
    opacity: 0.1,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 40,
  },

  // Header
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 24,
    paddingTop: Platform.OS === 'ios' ? 60 : 48,
    marginBottom: 16,
  },
  greeting: {
    fontSize: 15,
    color: 'rgba(255,255,255,0.55)',
    fontWeight: '500',
  },
  userName: {
    fontSize: 26,
    fontWeight: '800',
    color: '#fff',
    marginTop: 2,
  },
  rolePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 4,
    backgroundColor: 'rgba(46,163,242,0.12)',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
    alignSelf: 'flex-start',
  },
  roleText: {
    fontSize: 10,
    fontWeight: '600',
    color: colors.brand[300],
    textTransform: 'capitalize',
  },
  avatarBtn: {
    padding: 4,
  },

  // Brand pill
  brandPill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'center',
    backgroundColor: 'rgba(46,163,242,0.08)',
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 6,
    gap: 8,
    marginBottom: 20,
  },
  brandPillAccent: {
    width: 3,
    height: 14,
    borderRadius: 1.5,
    backgroundColor: colors.brand[400],
  },
  brandPillText: {
    fontSize: 13,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.7)',
    letterSpacing: 2,
  },
  brandPillBold: {
    fontWeight: '700',
    color: 'rgba(255,255,255,0.9)',
  },

  // KPI Section
  kpiSection: {
    paddingHorizontal: 24,
    marginBottom: 24,
  },
  kpiSectionTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: 'rgba(255,255,255,0.7)',
    marginBottom: 10,
  },
  kpiGrid: {
    flexDirection: 'row',
    gap: 8,
  },
  kpiCard: {
    flex: 1,
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderRadius: 14,
    padding: 12,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  kpiValue: {
    fontSize: 20,
    fontWeight: '800',
    color: '#fff',
    marginTop: 6,
  },
  kpiLabel: {
    fontSize: 10,
    fontWeight: '600',
    color: 'rgba(255,255,255,0.45)',
    marginTop: 2,
  },
  ratesRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 8,
  },
  rateChip: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderRadius: 8,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)',
  },
  rateValue: {
    fontSize: 13,
    fontWeight: '800',
    color: colors.brand[300],
  },
  rateLabel: {
    fontSize: 10,
    fontWeight: '500',
    color: 'rgba(255,255,255,0.35)',
  },
  kpiLoading: {
    paddingVertical: 20,
    alignItems: 'center',
  },
  totalAmountBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginTop: 8,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  totalAmountLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: 'rgba(255,255,255,0.5)',
  },
  totalAmountValue: {
    fontSize: 14,
    fontWeight: '800',
    color: colors.brand[300],
  },

  // Hero Section
  heroSection: {
    alignItems: 'center',
    paddingHorizontal: 24,
    marginBottom: 36,
  },
  heroTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#fff',
    marginBottom: 8,
    textAlign: 'center',
  },
  heroSubtitle: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.5)',
    textAlign: 'center',
    lineHeight: 20,
    maxWidth: 280,
    marginBottom: 32,
  },
  cameraWrapper: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 140,
    height: 140,
    marginBottom: 16,
  },
  cameraRingOuter: {
    position: 'absolute',
    width: 140,
    height: 140,
    borderRadius: 70,
    borderWidth: 2,
    borderColor: 'rgba(46,163,242,0.25)',
  },
  cameraBtn: {
    width: 110,
    height: 110,
    borderRadius: 55,
    backgroundColor: 'rgba(46,163,242,0.12)',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: 'rgba(46,163,242,0.25)',
  },
  cameraBtnInner: {
    width: 84,
    height: 84,
    borderRadius: 42,
    backgroundColor: colors.brand[400],
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: colors.brand[400],
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.4,
    shadowRadius: 16,
    elevation: 8,
  },
  cameraTip: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.35)',
    fontWeight: '500',
  },

  // Quick Actions
  actionsSection: {
    paddingHorizontal: 24,
    marginBottom: 24,
  },
  actionsTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#fff',
    marginBottom: 14,
  },
  actionsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    rowGap: 10,
  },
  actionCard: {
    width: (width - 48 - 20) / 3,
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 6,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  actionIcon: {
    width: 40,
    height: 40,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 8,
  },
  actionLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: '#fff',
    textAlign: 'center',
    marginBottom: 2,
  },
  actionDesc: {
    fontSize: 9,
    color: 'rgba(255,255,255,0.4)',
    textAlign: 'center',
    lineHeight: 12,
  },

  // Stats
  statsSection: {
    paddingHorizontal: 24,
  },
  statsCard: {
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderRadius: 18,
    padding: 20,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  statsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    marginBottom: 14,
  },
  statItem: {
    alignItems: 'center',
    gap: 6,
  },
  statLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: 'rgba(255,255,255,0.55)',
  },
  statDivider: {
    width: 1,
    height: 24,
    backgroundColor: 'rgba(255,255,255,0.1)',
  },
});

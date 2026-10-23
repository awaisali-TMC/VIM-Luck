import React, { useState, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  ScrollView,
  Platform,
  Animated,
  Alert,
  Image,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { colors } from '../src/utils/colors';
import { loginInternal } from '../src/services/authService';

const tmcLogo = require('../assets/tmc-logo-dark.png');

export default function LoginScreen() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  // Animations
  const logoScale = useRef(new Animated.Value(0)).current;
  const formOpacity = useRef(new Animated.Value(0)).current;
  const formTranslateY = useRef(new Animated.Value(30)).current;

  React.useEffect(() => {
    Animated.sequence([
      Animated.spring(logoScale, {
        toValue: 1,
        tension: 50,
        friction: 7,
        useNativeDriver: true,
      }),
      Animated.parallel([
        Animated.timing(formOpacity, {
          toValue: 1,
          duration: 500,
          useNativeDriver: true,
        }),
        Animated.timing(formTranslateY, {
          toValue: 0,
          duration: 500,
          useNativeDriver: true,
        }),
      ]),
    ]).start();
  }, []);

  const handleLogin = async () => {
    if (!email.trim()) {
      Alert.alert('Missing Email', 'Please enter your email address.');
      return;
    }
    if (!password.trim()) {
      Alert.alert('Missing Password', 'Please enter your password.');
      return;
    }

    setLoading(true);
    try {
      await loginInternal(email.trim(), password.trim());
      router.replace('/home');
    } catch (err: any) {
      const msg =
        err.response?.data?.detail ||
        err.message ||
        'Login failed. Please check your credentials.';
      Alert.alert('Login Failed', msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      {/* Background */}
      <View style={styles.bgTop} pointerEvents="none" />
      <View style={styles.bgBottom} pointerEvents="none" />
      <View style={styles.bgAccent} pointerEvents="none" />

      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        bounces={false}
        showsVerticalScrollIndicator={false}
      >
        {/* Brand */}
        <Animated.View style={[styles.brandSection, { transform: [{ scale: logoScale }] }]}>
          <View style={styles.brandRow}>
            <View style={styles.logoAccent} />
            <Text style={styles.brandName}>cogni<Text style={styles.brandNameBold}>vend</Text></Text>
          </View>
          <Text style={styles.brandTagline}>
            Vendor Compliance & Invoice Automation
          </Text>
        </Animated.View>

        {/* Form Card */}
        <Animated.View
          style={[
            styles.formCard,
            {
              opacity: formOpacity,
              transform: [{ translateY: formTranslateY }],
            },
          ]}
        >
          <Text style={styles.welcomeTitle}>Welcome back</Text>
          <Text style={styles.welcomeSub}>Sign in to your account</Text>

          {/* Email */}
          <View style={styles.inputContainer}>
            <Ionicons
              name="mail-outline"
              size={18}
              color={colors.neutral[400]}
              style={styles.inputIcon}
            />
            <TextInput
              style={styles.input}
              placeholder="Email address"
              placeholderTextColor={colors.neutral[400]}
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="off"
              returnKeyType="next"
            />
          </View>

          {/* Password */}
          <View style={styles.inputContainer}>
            <Ionicons
              name="lock-closed-outline"
              size={18}
              color={colors.neutral[400]}
              style={styles.inputIcon}
            />
            <TextInput
              style={styles.input}
              placeholder="Password"
              placeholderTextColor={colors.neutral[400]}
              value={password}
              onChangeText={setPassword}
              secureTextEntry={!showPassword}
              autoComplete="off"
              returnKeyType="done"
              onSubmitEditing={handleLogin}
            />
            <TouchableOpacity
              onPress={() => setShowPassword(!showPassword)}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              <Ionicons
                name={showPassword ? 'eye-off-outline' : 'eye-outline'}
                size={18}
                color={colors.neutral[400]}
              />
            </TouchableOpacity>
          </View>

          {/* Sign In */}
          <TouchableOpacity
            style={[styles.signInBtn, loading && styles.signInBtnLoading]}
            onPress={handleLogin}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading ? (
              <View style={styles.btnInner}>
                <Ionicons name="sync" size={18} color="#fff" />
                <Text style={styles.signInText}>Signing in...</Text>
              </View>
            ) : (
              <View style={styles.btnInner}>
                <Text style={styles.signInText}>Sign In</Text>
                <Ionicons name="arrow-forward" size={18} color="#fff" />
              </View>
            )}
          </TouchableOpacity>
        </Animated.View>

        {/* Powered By + TMC logo */}
        <View style={styles.poweredBy}>
          <Text style={styles.poweredByText}>Powered By</Text>
          <Image source={tmcLogo} style={styles.poweredByLogo} resizeMode="contain" />
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
  bgTop: {
    position: 'absolute',
    top: -120,
    right: -90,
    width: 320,
    height: 320,
    borderRadius: 160,
    backgroundColor: colors.brand[400],
    opacity: 0.08,
  },
  bgBottom: {
    position: 'absolute',
    bottom: -80,
    left: -60,
    width: 220,
    height: 220,
    borderRadius: 110,
    backgroundColor: colors.brand[600],
    opacity: 0.1,
  },
  bgAccent: {
    position: 'absolute',
    top: '35%',
    left: -30,
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: colors.brand[400],
    opacity: 0.06,
  },
  content: {
    flexGrow: 1,
    paddingHorizontal: 24,
    justifyContent: 'center',
  },

  // Brand
  brandSection: {
    alignItems: 'center',
    marginBottom: 32,
  },
  brandRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  logoAccent: {
    width: 4,
    height: 22,
    borderRadius: 2,
    backgroundColor: colors.brand[400],
    marginRight: 10,
  },
  brandName: {
    fontSize: 26,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.9)',
    letterSpacing: 3,
  },
  brandNameBold: {
    fontWeight: '700',
    color: '#fff',
  },
  brandTagline: {
    fontSize: 11,
    color: 'rgba(255,255,255,0.35)',
    fontWeight: '400',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
    textAlign: 'center',
  },

  // Form Card
  formCard: {
    backgroundColor: '#fff',
    borderRadius: 24,
    padding: 28,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 16 },
    shadowOpacity: 0.2,
    shadowRadius: 32,
    elevation: 14,
  },
  welcomeTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: colors.neutral[900],
    marginBottom: 4,
  },
  welcomeSub: {
    fontSize: 14,
    color: colors.neutral[500],
    marginBottom: 24,
  },

  // Inputs
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.neutral[50],
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: colors.neutral[200],
    paddingHorizontal: 14,
    height: 52,
    marginBottom: 14,
  },
  inputIcon: {
    marginRight: 10,
  },
  input: {
    flex: 1,
    fontSize: 15,
    color: colors.neutral[800],
  },

  // Sign In Button
  signInBtn: {
    backgroundColor: colors.brand[400],
    borderRadius: 14,
    height: 52,
    marginTop: 8,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: colors.brand[400],
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 10,
    elevation: 5,
  },
  signInBtnLoading: {
    opacity: 0.85,
  },
  btnInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  signInText: {
    fontSize: 16,
    fontWeight: '700',
    color: '#fff',
  },

  // Powered by
  poweredBy: {
    alignItems: 'center',
    marginTop: 20,
  },
  poweredByText: {
    fontSize: 11,
    color: 'rgba(255,255,255,0.5)',
    fontWeight: '600',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    marginBottom: 6,
  },
  poweredByLogo: {
    width: 48,
    height: 48,
  },
});

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  TouchableOpacity,
  Alert,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../../src/utils/colors';

const DEFAULT_API_URL = 'https://einv-backend.onrender.com';

export default function SettingsScreen() {
  const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem('api_base_url').then((url) => {
      if (url) setApiUrl(url);
    });
  }, []);

  const handleSave = async () => {
    try {
      // Trim trailing slash
      const cleaned = apiUrl.replace(/\/+$/, '');
      await AsyncStorage.setItem('api_base_url', cleaned);
      setApiUrl(cleaned);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      Alert.alert('Error', 'Failed to save API URL.');
    }
  };

  const handleReset = () => {
    Alert.alert('Reset API URL', `Reset to default?\n${DEFAULT_API_URL}`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Reset',
        onPress: async () => {
          await AsyncStorage.setItem('api_base_url', DEFAULT_API_URL);
          setApiUrl(DEFAULT_API_URL);
        },
      },
    ]);
  };

  const handleClearCache = () => {
    Alert.alert('Clear Cache', 'This will clear all cached data. Continue?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Clear',
        style: 'destructive',
        onPress: async () => {
          try {
            const keys = await AsyncStorage.getAllKeys();
            const cacheKeys = keys.filter((k) => k !== 'api_base_url');
            if (cacheKeys.length > 0) {
              await AsyncStorage.multiRemove(cacheKeys);
            }
            Alert.alert('Done', 'Cache cleared.');
          } catch {
            Alert.alert('Error', 'Failed to clear cache.');
          }
        },
      },
    ]);
  };

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {/* API Configuration */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>API Configuration</Text>
          <View style={styles.card}>
            <Text style={styles.label}>Backend URL</Text>
            <TextInput
              style={styles.input}
              value={apiUrl}
              onChangeText={setApiUrl}
              placeholder="https://einv-backend.onrender.com"
              placeholderTextColor={colors.neutral[400]}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
            />
            <View style={styles.row}>
              <TouchableOpacity style={styles.saveBtn} onPress={handleSave}>
                <Ionicons
                  name={saved ? 'checkmark-circle' : 'save-outline'}
                  size={16}
                  color="#fff"
                />
                <Text style={styles.saveBtnText}>{saved ? 'Saved!' : 'Save'}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.resetBtn} onPress={handleReset}>
                <Text style={styles.resetBtnText}>Reset to Default</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>

        {/* Data Management */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Data</Text>
          <View style={styles.card}>
            <TouchableOpacity style={styles.dangerBtn} onPress={handleClearCache}>
              <Ionicons name="trash-outline" size={16} color={colors.danger[600]} />
              <Text style={styles.dangerBtnText}>Clear Cache</Text>
            </TouchableOpacity>
            <Text style={styles.hint}>
              Removes locally cached invoice data. Your invoices on the server are not affected.
            </Text>
          </View>
        </View>

        {/* About */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>About</Text>
          <View style={styles.card}>
            <View style={styles.aboutRow}>
              <Text style={styles.aboutLabel}>App</Text>
              <Text style={styles.aboutValue}>Cognivend</Text>
            </View>
            <View style={styles.aboutRow}>
              <Text style={styles.aboutLabel}>Version</Text>
              <Text style={styles.aboutValue}>1.0.0</Text>
            </View>
            <View style={styles.aboutRow}>
              <Text style={styles.aboutLabel}>Platform</Text>
              <Text style={styles.aboutValue}>{Platform.OS} ({Platform.Version})</Text>
            </View>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: {
    flex: 1,
    backgroundColor: colors.neutral[50],
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.neutral[500],
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: colors.neutral[200],
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.neutral[700],
    marginBottom: 6,
  },
  input: {
    borderWidth: 1,
    borderColor: colors.neutral[300],
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    color: colors.neutral[800],
    backgroundColor: colors.neutral[50],
    marginBottom: 12,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  saveBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.brand[600],
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
  },
  saveBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  resetBtn: {
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  resetBtnText: {
    color: colors.neutral[500],
    fontSize: 13,
    fontWeight: '500',
  },
  dangerBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderColor: colors.danger[200],
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
    alignSelf: 'flex-start',
  },
  dangerBtnText: {
    color: colors.danger[600],
    fontSize: 13,
    fontWeight: '600',
  },
  hint: {
    fontSize: 12,
    color: colors.neutral[400],
    marginTop: 10,
    lineHeight: 16,
  },
  aboutRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[100],
  },
  aboutLabel: {
    fontSize: 13,
    color: colors.neutral[500],
  },
  aboutValue: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.neutral[800],
  },
});

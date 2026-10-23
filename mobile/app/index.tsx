import { Redirect } from 'expo-router';
import { useEffect, useState } from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { colors } from '../src/utils/colors';
import { getMe } from '../src/services/authService';

export default function Index() {
  const [checking, setChecking] = useState(true);
  const [loggedIn, setLoggedIn] = useState(false);

  useEffect(() => {
    getMe().then((user) => {
      setLoggedIn(!!user);
      setChecking(false);
    }).catch(() => {
      setLoggedIn(false);
      setChecking(false);
    });
  }, []);

  if (checking) {
    return (
      <View style={styles.splash}>
        <ActivityIndicator size="large" color={colors.brand[500]} />
      </View>
    );
  }

  if (loggedIn) {
    return <Redirect href="/home" />;
  }

  return <Redirect href="/login" />;
}

const styles = StyleSheet.create({
  splash: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.brand[600],
  },
});

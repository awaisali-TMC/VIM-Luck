import { Stack } from 'expo-router';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StatusBar } from 'expo-status-bar';
import { colors } from '../src/utils/colors';

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: colors.neutral[50] },
            animation: 'slide_from_right',
          }}
        >
          <Stack.Screen name="index" />
          <Stack.Screen
            name="login"
            options={{
              animation: 'fade',
              gestureEnabled: false,
            }}
          />
          <Stack.Screen
            name="home"
            options={{
              animation: 'fade',
              gestureEnabled: false,
            }}
          />
          <Stack.Screen name="(tabs)" options={{ gestureEnabled: false }} />
          <Stack.Screen
            name="scanner"
            options={{
              headerShown: false,
              animation: 'slide_from_bottom',
              presentation: 'fullScreenModal',
            }}
          />
          <Stack.Screen
            name="extraction-results"
            options={{
              headerShown: true,
              title: 'Extraction Results',
              headerTintColor: colors.brand[600],
              headerStyle: { backgroundColor: '#fff' },
              presentation: 'card',
            }}
          />
          <Stack.Screen
            name="invoice/[id]"
            options={{
              headerShown: true,
              title: 'Invoice Detail',
              headerTintColor: colors.brand[600],
              headerStyle: { backgroundColor: '#fff' },
              presentation: 'card',
            }}
          />
          <Stack.Screen
            name="purchase-orders"
            options={{
              headerShown: false,
              presentation: 'card',
            }}
          />
          <Stack.Screen
            name="po/[id]"
            options={{
              headerShown: true,
              title: 'PO Detail',
              headerTintColor: colors.brand[600],
              headerStyle: { backgroundColor: '#fff' },
              presentation: 'card',
            }}
          />
          <Stack.Screen
            name="po/create"
            options={{
              headerShown: false,
              presentation: 'card',
            }}
          />
          <Stack.Screen
            name="inbox"
            options={{
              headerShown: false,
              presentation: 'card',
            }}
          />
          <Stack.Screen
            name="email/[id]"
            options={{
              headerShown: true,
              title: 'Email Detail',
              headerTintColor: colors.brand[600],
              headerStyle: { backgroundColor: '#fff' },
              presentation: 'card',
            }}
          />
        </Stack>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

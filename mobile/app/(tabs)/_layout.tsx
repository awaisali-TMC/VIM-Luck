import { Tabs, useRouter } from 'expo-router';
import { TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../../src/utils/colors';

export default function TabLayout() {
  const router = useRouter();
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: '#fff', shadowColor: 'transparent', elevation: 0 },
        headerTitleStyle: { fontWeight: '700', fontSize: 18, color: colors.neutral[900] },
        tabBarActiveTintColor: colors.brand[500],
        tabBarInactiveTintColor: colors.neutral[400],
        tabBarStyle: {
          backgroundColor: '#fff',
          borderTopColor: colors.neutral[100],
          paddingTop: 4,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
      }}
    >
      <Tabs.Screen
        name="upload"
        options={{
          title: 'Upload',
          headerTitle: 'Upload Invoice',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="cloud-upload-outline" size={size} color={color} />
          ),
          headerLeft: () => (
            <TouchableOpacity
              onPress={() => router.replace('/home')}
              style={{ marginLeft: 16 }}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              <Ionicons name="home-outline" size={22} color={colors.neutral[600]} />
            </TouchableOpacity>
          ),
        }}
      />
      <Tabs.Screen
        name="approvals"
        options={{
          title: 'Approvals',
          headerTitle: 'Status Tracker',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="checkmark-done-circle-outline" size={size} color={color} />
          ),
          headerLeft: () => (
            <TouchableOpacity
              onPress={() => router.replace('/home')}
              style={{ marginLeft: 16 }}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              <Ionicons name="home-outline" size={22} color={colors.neutral[600]} />
            </TouchableOpacity>
          ),
        }}
      />
      <Tabs.Screen
        name="invoices"
        options={{
          title: 'Invoices',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="document-text-outline" size={size} color={color} />
          ),
          headerLeft: () => (
            <TouchableOpacity
              onPress={() => router.replace('/home')}
              style={{ marginLeft: 16 }}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              <Ionicons name="home-outline" size={22} color={colors.neutral[600]} />
            </TouchableOpacity>
          ),
          headerRight: () => (
            <TouchableOpacity
              onPress={() => router.push('/scanner')}
              style={{ marginRight: 16 }}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              <Ionicons name="camera-outline" size={22} color={colors.brand[500]} />
            </TouchableOpacity>
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Settings',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="settings-outline" size={size} color={color} />
          ),
        }}
      />
    </Tabs>
  );
}

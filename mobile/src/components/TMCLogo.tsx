import React from 'react';
import { View, Image, StyleSheet } from 'react-native';

/**
 * Two logo assets:
 *  - tmc-logo.png       → original colours on white bg  (for light surfaces)
 *  - tmc-logo-dark.png  → white TMC text + green/grey tally on transparent bg (for dark surfaces)
 */
const logoLight = require('../../assets/tmc-logo.png');
const logoDark = require('../../assets/tmc-logo-dark.png');

interface Props {
  /** Height & width in px (1:1 aspect). */
  size?: number;
  /** 0-1 opacity. */
  opacity?: number;
  /**
   * 'light' → white-text variant for dark backgrounds (login, home navy screens).
   * 'dark'  → original colours for light backgrounds (white cards, settings).
   */
  variant?: 'light' | 'dark';
}

export default function TMCLogo({ size = 48, opacity = 1, variant = 'light' }: Props) {
  const source = variant === 'light' ? logoDark : logoLight;

  return (
    <View style={[styles.container, { opacity }]}>
      <Image
        source={source}
        style={{ width: size, height: size }}
        resizeMode="contain"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});

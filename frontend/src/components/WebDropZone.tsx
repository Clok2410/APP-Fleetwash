import React from "react";
import { View, ViewStyle } from "react-native";

type Props = {
  onFile: (file: File) => void;
  style?: ViewStyle;
  children?: React.ReactNode;
};

// Native: drag-and-drop is a web concept. Just render the children passthrough.
export default function WebDropZone({ children, style }: Props) {
  return <View style={style}>{children}</View>;
}

/**
 * PFAA Banner — Static header with pearl shimmer aesthetic
 */

import React, { useMemo } from 'react';
import { Box, Text, Static } from 'ink';

interface BannerProps {
  version: string;
  toolCount?: number;
  mcpCount?: number;
  memoryLayers?: number;
  hookCount?: number;
}

export function Banner({ version, toolCount = 44, mcpCount = 17, memoryLayers = 5, hookCount = 6 }: BannerProps) {
  const banner = useMemo(() => ({
    id: 'banner',
    version,
    toolCount,
    mcpCount,
    memoryLayers,
    hookCount,
  }), [version, toolCount, mcpCount, memoryLayers, hookCount]);

  return (
    <Static items={[banner]}>
      {(item) => (
        <Box key={item.id} flexDirection="column" paddingLeft={2} marginBottom={1}>
          <Text bold>
            <Text color="#FFFFFF">A</Text>
            <Text color="#FFE4E1">U</Text>
            <Text color="#E6E6FA">S</Text>
            <Text color="#E0F7FA">S</Text>
            <Text color="#FFF8E1">I</Text>
            <Text color="#F8F8FF">E</Text>
            <Text>  </Text>
            <Text color="#E6E6FA">A</Text>
            <Text color="#FFE4E1">G</Text>
            <Text color="#E0F7FA">E</Text>
            <Text color="#FFFFFF">N</Text>
            <Text color="#FFF8E1">T</Text>
            <Text color="#F8F8FF">S</Text>
          </Text>
          <Text color="#D4D4D8">{'━'.repeat(64)}</Text>
          <Text>
            <Text color="#8E8E93">v{item.version}</Text>
            <Text color="#D4D4D8"> │ </Text>
            <Text color="#F8F8FF" bold>{item.toolCount}</Text>
            <Text color="#E8D5B7"> Tools</Text>
            <Text color="#D4D4D8"> │ </Text>
            <Text color="#B5D4FF" bold>{item.mcpCount}</Text>
            <Text color="#B5D4FF"> MCP</Text>
            <Text color="#D4D4D8"> │ </Text>
            <Text color="#E6E6FA" bold>{item.memoryLayers}</Text>
            <Text color="#E6E6FA">-Layer Memory</Text>
            <Text color="#D4D4D8"> │ </Text>
            <Text color="#FFE4E1" bold>{item.hookCount}</Text>
            <Text color="#FFE4E1"> Hooks</Text>
            <Text color="#D4D4D8"> │ </Text>
            <Text color="#A8E6CF" bold>Py</Text>
            <Text color="#A8E6CF"> 3.15</Text>
          </Text>
        </Box>
      )}
    </Static>
  );
}

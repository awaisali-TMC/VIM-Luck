/* eslint-disable react-refresh/only-export-components -- context file intentionally exports the provider + its hook together */
import { createContext, useContext } from "react";
import { pageLevel, canAccessPath, canEditPage } from "../config/rolePermissions";

const PermissionsContext = createContext({ matrix: null, role: null, roles: [] });

/**
 * Provides the live role→page level matrix (and the dynamic role list) to any
 * page that needs finer checks than the route guard — e.g. the invoice detail
 * page deciding view-only vs editable.
 */
export function PermissionsProvider({ matrix, role, roles = [], children }) {
  return (
    <PermissionsContext.Provider value={{ matrix, role, roles }}>
      {children}
    </PermissionsContext.Provider>
  );
}

export function usePermissions() {
  const { matrix, role, roles } = useContext(PermissionsContext);
  return {
    matrix,
    role,
    roles,
    level: (path) => pageLevel(role, path, matrix),
    canAccess: (path) => canAccessPath(role, path, matrix),
    canEdit: (path) => canEditPage(role, path, matrix),
  };
}

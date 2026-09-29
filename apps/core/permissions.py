"""Custom role-based permission classes for SADACO ERP/CRM."""
from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, 'role', None) == 'admin')


class IsSalesOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, 'role', None) in ('sales', 'admin'))


class IsOperationsOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, 'role', None) in ('operations', 'admin'))


class IsFinanceOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, 'role', None) in ('finance', 'admin'))


class IsSalesOrOperationsOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated
                    and getattr(u, 'role', None) in ('sales', 'operations', 'admin'))


class ReadOnlyOrAdmin(BasePermission):
    """Anyone authenticated can read; only admin can write."""
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return getattr(u, 'role', None) == 'admin'

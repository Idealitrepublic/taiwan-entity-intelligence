"""Vercel entry point for Taiwan Entity Intelligence."""

# Vercel's Python runtime looks for a BaseHTTPRequestHandler-compatible
# class named ``handler`` in an ``api`` function.
from src.server import Handler as handler

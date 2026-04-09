"""
Módulo de Análisis de Datos
Soporta: CSV, Excel, JSON, SQLite
"""

import pandas as pd
import numpy as np
import json
import sqlite3
import io
from datetime import datetime
import logging

logger = logging.getLogger('cic_ia.data_analysis')

class DataAnalysisModule:
    def __init__(self):
        self.supported_formats = ['.csv', '.xlsx', '.xls', '.json', '.db', '.sqlite']
        self.current_df = None
        self.file_name = None
    
    def load_file(self, file_path, file_type=None):
        """Carga archivo de datos"""
        try:
            if file_path.endswith('.csv'):
                self.current_df = pd.read_csv(file_path)
            elif file_path.endswith(('.xlsx', '.xls')):
                self.current_df = pd.read_excel(file_path)
            elif file_path.endswith('.json'):
                self.current_df = pd.read_json(file_path)
            elif file_path.endswith(('.db', '.sqlite')):
                conn = sqlite3.connect(file_path)
                # Obtener tablas
                tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)
                if len(tables) > 0:
                    self.current_df = pd.read_sql(f"SELECT * FROM {tables.iloc[0]['name']}", conn)
                conn.close()
            else:
                return {'error': f'Formato no soportado. Use: {self.supported_formats}'}
            
            self.file_name = file_path
            return {
                'success': True,
                'columns': list(self.current_df.columns),
                'rows': len(self.current_df),
                'preview': self.current_df.head(5).to_dict('records')
            }
            
        except Exception as e:
            logger.error(f"Error cargando archivo: {e}")
            return {'error': str(e)}
    
    def analyze(self, query):
        """Analiza datos según consulta en lenguaje natural"""
        if self.current_df is None:
            return {'error': 'No hay datos cargados. Sube un archivo primero.'}
        
        query_lower = query.lower()
        
        # Detectar tipo de análisis
        if any(kw in query_lower for kw in ['mejor vendedor', 'top vendedor', 'vendedor con más ventas']):
            return self._best_seller_analysis()
        
        elif any(kw in query_lower for kw in ['producto más vendido', 'producto top', 'mejor producto']):
            return self._best_product_analysis()
        
        elif any(kw in query_lower for kw in ['ventas del mes', 'ventas por mes', 'total mensual']):
            return self._monthly_sales_analysis()
        
        elif any(kw in query_lower for kw in ['promedio', 'media', 'average']):
            return self._statistical_analysis('mean')
        
        elif any(kw in query_lower for kw in ['máximo', 'máx', 'max', 'mayor']):
            return self._statistical_analysis('max')
        
        elif any(kw in query_lower for kw in ['mínimo', 'mín', 'min', 'menor']):
            return self._statistical_analysis('min')
        
        elif any(kw in query_lower for kw in ['gráfico', 'grafico', 'chart', 'plot']):
            return self._generate_chart(query)
        
        else:
            # Análisis general
            return self._general_summary()
    
    def _best_seller_analysis(self):
        """Encuentra el mejor vendedor"""
        # Buscar columna de vendedor y ventas
        vendedor_col = None
        ventas_col = None
        
        for col in self.current_df.columns:
            col_lower = col.lower()
            if any(kw in col_lower for kw in ['vendedor', 'seller', 'empleado', 'agente']):
                vendedor_col = col
            if any(kw in col_lower for kw in ['venta', 'monto', 'total', 'precio', 'ingreso', 'sales', 'amount']):
                ventas_col = col
        
        if not vendedor_col or not ventas_col:
            return {'error': f'No encontré columnas de vendedor/ventas. Columnas disponibles: {list(self.current_df.columns)}'}
        
        # Agrupar por vendedor
        sales_by_seller = self.current_df.groupby(vendedor_col)[ventas_col].sum().sort_values(ascending=False)
        
        return {
            'analysis_type': 'best_seller',
            'result': {
                'best_seller': sales_by_seller.index[0],
                'total_sales': float(sales_by_seller.iloc[0]),
                'ranking': sales_by_seller.head(10).to_dict()
            },
            'summary': f"🏆 Mejor vendedor: **{sales_by_seller.index[0]}** con ${sales_by_seller.iloc[0]:,.2f} en ventas"
        }
    
    def _best_product_analysis(self):
        """Encuentra el producto más vendido"""
        producto_col = None
        cantidad_col = None
        
        for col in self.current_df.columns:
            col_lower = col.lower()
            if any(kw in col_lower for kw in ['producto', 'product', 'item', 'artículo', 'articulo']):
                producto_col = col
            if any(kw in col_lower for kw in ['cantidad', 'quantity', 'unidades', 'vendidos']):
                cantidad_col = col
        
        if not producto_col:
            return {'error': f'No encontré columna de producto. Columnas: {list(self.current_df.columns)}'}
        
        # Si hay cantidad, usarla; si no, contar ocurrencias
        if cantidad_col:
            product_sales = self.current_df.groupby(producto_col)[cantidad_col].sum().sort_values(ascending=False)
        else:
            product_sales = self.current_df[producto_col].value_counts()
        
        return {
            'analysis_type': 'best_product',
            'result': {
                'best_product': product_sales.index[0],
                'total_sold': float(product_sales.iloc[0]),
                'top_10': product_sales.head(10).to_dict()
            },
            'summary': f"📦 Producto más vendido: **{product_sales.index[0]}** con {product_sales.iloc[0]:,.0f} unidades"
        }
    
    def _monthly_sales_analysis(self):
        """Análisis de ventas por mes"""
        # Buscar columna de fecha
        fecha_col = None
        ventas_col = None
        
        for col in self.current_df.columns:
            col_lower = col.lower()
            if any(kw in col_lower for kw in ['fecha', 'date', 'día', 'dia', 'mes']):
                fecha_col = col
            if any(kw in col_lower for kw in ['venta', 'monto', 'total', 'precio', 'sales']):
                ventas_col = col
        
        if not fecha_col:
            return {'error': f'No encontré columna de fecha. Columnas: {list(self.current_df.columns)}'}
        
        # Convertir a datetime
        self.current_df[fecha_col] = pd.to_datetime(self.current_df[fecha_col], errors='coerce')
        
        # Extraer mes
        self.current_df['mes'] = self.current_df[fecha_col].dt.to_period('M')
        
        if ventas_col:
            monthly = self.current_df.groupby('mes')[ventas_col].sum()
        else:
            monthly = self.current_df.groupby('mes').size()
        
        return {
            'analysis_type': 'monthly_sales',
            'result': {
                'monthly_totals': {str(k): float(v) for k, v in monthly.to_dict().items()},
                'best_month': str(monthly.idxmax()),
                'total_yearly': float(monthly.sum())
            },
            'summary': f"📅 Mejor mes: **{monthly.idxmax()}** con ${monthly.max():,.2f}. Total anual: ${monthly.sum():,.2f}"
        }
    
    def _statistical_analysis(self, operation):
        """Análisis estadístico"""
        numeric_cols = self.current_df.select_dtypes(include=[np.number]).columns
        
        if len(numeric_cols) == 0:
            return {'error': 'No hay columnas numéricas para analizar'}
        
        results = {}
        for col in numeric_cols:
            if operation == 'mean':
                results[col] = float(self.current_df[col].mean())
            elif operation == 'max':
                results[col] = {
                    'value': float(self.current_df[col].max()),
                    'row': self.current_df.loc[self.current_df[col].idxmax()].to_dict()
                }
            elif operation == 'min':
                results[col] = {
                    'value': float(self.current_df[col].min()),
                    'row': self.current_df.loc[self.current_df[col].idxmin()].to_dict()
                }
        
        op_names = {'mean': 'Promedio', 'max': 'Máximo', 'min': 'Mínimo'}
        return {
            'analysis_type': f'statistical_{operation}',
            'result': results,
            'summary': f"📊 {op_names[operation]}s: " + ", ".join([f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v['value']:.2f}" for k, v in list(results.items())[:3]])
        }
    
    def _generate_chart(self, query):
        """Genera gráfico (retorna datos para visualización)"""
        # Por ahora retorna datos para que el frontend genere el gráfico
        chart_type = 'bar' if 'barra' in query or 'bar' in query else \
                    'line' if 'línea' in query or 'line' in query else \
                    'pie' if 'pastel' in query or 'pie' in query else 'bar'
        
        return {
            'analysis_type': 'chart',
            'chart_type': chart_type,
            'data': self.current_df.head(20).to_dict('records'),
            'columns': list(self.current_df.columns)
        }
    
    def _general_summary(self):
        """Resumen general de los datos"""
        summary = {
            'total_rows': len(self.current_df),
            'total_columns': len(self.current_df.columns),
            'columns': list(self.current_df.columns),
            'numeric_summary': self.current_df.describe().to_dict() if len(self.current_df.select_dtypes(include=[np.number]).columns) > 0 else None,
            'missing_values': self.current_df.isnull().sum().to_dict(),
            'sample': self.current_df.head(3).to_dict('records')
        }
        
        return {
            'analysis_type': 'general_summary',
            'result': summary,
            'summary': f"📋 Dataset con **{summary['total_rows']:,}** filas y **{summary['total_columns']}** columnas: {', '.join(summary['columns'][:5])}..."
        }
    
    def export_results(self, format='json'):
        """Exporta resultados del análisis"""
        if self.current_df is None:
            return {'error': 'No hay datos para exportar'}
        
        if format == 'csv':
            return self.current_df.to_csv(index=False)
        elif format == 'excel':
            output = io.BytesIO()
            self.current_df.to_excel(output, index=False, engine='openpyxl')
            output.seek(0)
            return output.getvalue()
        else:
            return self.current_df.to_dict('records')

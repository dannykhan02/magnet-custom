import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import os
import logging
from datetime import datetime
from typing import Dict, Tuple, List, Optional
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SalesReportConfig:
    """Configuration class for sales report styling and colors."""
    
    # Define specific colors for each product category - using string hex values for matplotlib
    COLORS_BY_CATEGORY_MATPLOTLIB = {
        'FRIDGE_MAGNETS': '#FF8042',        # Orange
        'CUSTOM_PRINTS': '#FFBB28',         # Yellow
        'BUSINESS_CARDS': '#0088FE',        # Blue
        'STICKERS': '#00C49F',              # Green
        'PROMOTIONAL': '#FF6699',           # Pinkish
        'PHOTO_MAGNETS': '#AA336A',         # Purple
        'BULK_ORDERS': '#00FF00',           # Bright Green
        'SPECIALTY': '#8884D8',             # Light Purple
        'UNKNOWN_CATEGORY': '#A9A9A9',      # Darker Grey for unknown categories
    }

    # Separate color definitions for ReportLab (using HexColor objects)
    COLORS_BY_CATEGORY_REPORTLAB = {
        'FRIDGE_MAGNETS': colors.HexColor('#FF8042'),
        'CUSTOM_PRINTS': colors.HexColor('#FFBB28'),
        'BUSINESS_CARDS': colors.HexColor('#0088FE'),
        'STICKERS': colors.HexColor('#00C49F'),
        'PROMOTIONAL': colors.HexColor('#FF6699'),
        'PHOTO_MAGNETS': colors.HexColor('#AA336A'),
        'BULK_ORDERS': colors.HexColor('#00FF00'),
        'SPECIALTY': colors.HexColor('#8884D8'),
        'UNKNOWN_CATEGORY': colors.HexColor('#A9A9A9'),
    }

    # Extended color palette for dynamic category assignment
    EXTENDED_COLORS_MATPLOTLIB = [
        '#FF8042', '#FFBB28', '#0088FE', '#00C49F', '#FF6699', '#AA336A',
        '#00FF00', '#8884D8', '#FF1493', '#32CD32', '#FF4500', '#9932CC',
        '#FF69B4', '#228B22', '#FF8C00', '#9370DB', '#20B2AA', '#DC143C'
    ]
    
    EXTENDED_COLORS_REPORTLAB = [colors.HexColor(color) for color in EXTENDED_COLORS_MATPLOTLIB]

    # Fallback colors
    FALLBACK_COLOR_MATPLOTLIB = '#808080'
    FALLBACK_COLOR_REPORTLAB = colors.HexColor('#808080')

    # Chart styling
    CHART_STYLE = {
        'figure_facecolor': '#1e1e1e',
        'axes_facecolor': '#1e1e1e',
        'text_color': '#cccccc',
        'title_fontsize': 16,
        'label_fontsize': 12,
        'tick_fontsize': 10
    }

class DataValidator:
    """Utility class for validating report data."""
    
    @staticmethod
    def validate_report_data(report: Dict) -> bool:
        """Validate that the report contains the minimum required data."""
        required_fields = ['total_revenue', 'total_orders']
        return all(field in report for field in required_fields)
    
    @staticmethod
    def sanitize_category_name(category: str) -> str:
        """Sanitize category names for consistent mapping."""
        if not category or category.strip() == '':
            return 'UNKNOWN_CATEGORY'
        return str(category).upper().replace(' ', '_').replace('-', '_')
    
    @staticmethod
    def validate_numeric_data(data: Dict) -> Dict:
        """Ensure all numeric values are valid."""
        validated = {}
        for key, value in data.items():
            try:
                validated[key] = float(value) if value is not None else 0.0
            except (ValueError, TypeError):
                logger.warning(f"Invalid numeric value for {key}: {value}, setting to 0")
                validated[key] = 0.0
        return validated

class ChartGenerator:
    """Enhanced chart generation with better error handling and styling."""
    
    def __init__(self, config: SalesReportConfig = None):
        self.config = config or SalesReportConfig()
        self.validator = DataValidator()
    
    def _get_color_for_category(self, category: str, color_index: int = None) -> str:
        """Get appropriate color for a category, with fallback to indexed colors."""
        sanitized_category = self.validator.sanitize_category_name(category)
        
        # Try to get predefined color
        color = self.config.COLORS_BY_CATEGORY_MATPLOTLIB.get(sanitized_category)
        
        # If not found, use extended color palette with index
        if not color and color_index is not None:
            color_palette = self.config.EXTENDED_COLORS_MATPLOTLIB
            color = color_palette[color_index % len(color_palette)]
        
        return color or self.config.FALLBACK_COLOR_MATPLOTLIB
    
    def _setup_matplotlib_style(self):
        """Setup consistent matplotlib styling."""
        plt.style.use('default')  # Reset to default first
        
    def generate_revenue_chart(self, report: Dict, path: str = "revenue_chart.png") -> str:
        """Generate an enhanced donut chart for Revenue by Product Category."""
        try:
            # Validate report data
            if not self.validator.validate_report_data(report):
                logger.warning("Invalid report data for revenue chart")
                return self._create_error_chart(path, "Invalid Data")

            # Extract and validate revenue data
            revenue_data = report.get('revenue_by_category', {})
            if not revenue_data:
                revenue_data = {'Total Sales': report.get('total_revenue', 0)}

            revenue_data = self.validator.validate_numeric_data(revenue_data)
            
            # Filter out zero values
            revenue_data = {k: v for k, v in revenue_data.items() if v > 0}
            
            if not revenue_data:
                return self._create_no_data_chart(path, "No Revenue Data Available")

            # Prepare data for plotting
            labels = list(revenue_data.keys())
            values = list(revenue_data.values())
            
            # Generate colors
            chart_colors = [self._get_color_for_category(label, i) for i, label in enumerate(labels)]

            # Create the chart
            fig, ax = plt.subplots(figsize=(10, 8), facecolor=self.config.CHART_STYLE['figure_facecolor'])
            ax.set_facecolor(self.config.CHART_STYLE['axes_facecolor'])

            # Enhanced autopct function
            def make_autopct(values):
                def my_autopct(pct):
                    absolute = int(pct/100.*sum(values))
                    return f'${absolute:,.0f}\n({pct:.1f}%)'
                return my_autopct

            # Create the pie chart with enhanced styling
            wedges, texts, autotexts = ax.pie(
                values,
                labels=[label.replace('_', ' ').title() for label in labels],
                colors=chart_colors,
                autopct=make_autopct(values),
                startangle=90,
                pctdistance=0.85,
                textprops={'color': self.config.CHART_STYLE['text_color'], 'fontsize': 10, 'weight': 'bold'}
            )

            # Create donut effect
            centre_circle = plt.Circle((0, 0), 0.70, fc='#2a2a2a', linewidth=2, edgecolor='#4a4a4a')
            fig.gca().add_artist(centre_circle)

            # Enhanced center text
            total_revenue = sum(values)
            center_text = f'Total Revenue\n${total_revenue:,.2f}'
            if len(revenue_data) > 1:
                avg_category_revenue = total_revenue / len(revenue_data)
                center_text += f'\n\nAvg per Category\n${avg_category_revenue:,.2f}'
            
            ax.text(0, 0, center_text, ha='center', va='center', 
                   color=self.config.CHART_STYLE['text_color'], fontsize=11, weight='bold')

            # Enhanced styling
            ax.axis('equal')
            plt.title(f'Revenue by Product Category\nTotal: ${total_revenue:,.2f}', 
                     color=self.config.CHART_STYLE['text_color'], 
                     fontsize=self.config.CHART_STYLE['title_fontsize'], 
                     pad=20, weight='bold')
            
            plt.tight_layout()
            plt.savefig(path, transparent=False, dpi=300, bbox_inches='tight', 
                       facecolor=fig.get_facecolor(), edgecolor='none')
            
            logger.info(f"Enhanced revenue chart saved to {path}")
            return path

        except Exception as e:
            logger.error(f"Error generating revenue chart: {e}")
            return self._create_error_chart(path, "Chart Generation Error")
        finally:
            plt.close('all')

    def generate_product_sales_chart(self, report: Dict, path: str = "product_sales_chart.png") -> str:
        """Generate an enhanced horizontal bar chart for top-selling products."""
        try:
            products_data = report.get('top_products', {})
            
            if not products_data:
                return self._create_no_data_chart(path, "No Product Sales Data")

            # Validate and sort data
            products_data = self.validator.validate_numeric_data(products_data)
            products_data = {k: v for k, v in products_data.items() if v > 0}
            
            if not products_data:
                return self._create_no_data_chart(path, "No Product Sales Data")

            # Sort and get top products
            sorted_products = sorted(products_data.items(), key=lambda x: x[1], reverse=True)
            top_products = sorted_products[:12]  # Increased to show more products
            
            product_names = [name[:30] + '...' if len(name) > 30 else name for name, _ in top_products]
            quantities = [qty for _, qty in top_products]

            # Create enhanced bar chart
            fig, ax = plt.subplots(figsize=(12, 8), facecolor=self.config.CHART_STYLE['figure_facecolor'])
            ax.set_facecolor(self.config.CHART_STYLE['axes_facecolor'])

            # Create gradient-like colors
            colors_list = plt.cm.viridis(np.linspace(0.3, 0.9, len(quantities)))
            
            bars = ax.barh(product_names, quantities, color=colors_list, alpha=0.8, edgecolor='white', linewidth=0.5)
            
            # Enhanced value labels
            max_qty = max(quantities)
            for i, (bar, qty) in enumerate(zip(bars, quantities)):
                # Position label based on bar length
                label_x = bar.get_width() + max_qty * 0.01 if bar.get_width() < max_qty * 0.7 else bar.get_width() * 0.95
                label_color = '#cccccc' if bar.get_width() < max_qty * 0.7 else '#1e1e1e'
                ha = 'left' if bar.get_width() < max_qty * 0.7 else 'right'
                
                ax.text(label_x, bar.get_y() + bar.get_height()/2,
                       f'{qty:,}', ha=ha, va='center', color=label_color, 
                       fontsize=9, weight='bold')

            # Enhanced styling
            ax.set_xlabel('Quantity Sold', color=self.config.CHART_STYLE['text_color'], 
                         fontsize=self.config.CHART_STYLE['label_fontsize'], weight='bold')
            ax.set_ylabel('Products', color=self.config.CHART_STYLE['text_color'], 
                         fontsize=self.config.CHART_STYLE['label_fontsize'], weight='bold')
            ax.set_title(f'Top {len(top_products)} Selling Products\nTotal Units: {sum(quantities):,}', 
                        color=self.config.CHART_STYLE['text_color'], 
                        fontsize=self.config.CHART_STYLE['title_fontsize'], pad=20, weight='bold')
            
            # Style axes
            ax.tick_params(colors=self.config.CHART_STYLE['text_color'], labelsize=self.config.CHART_STYLE['tick_fontsize'])
            ax.spines['bottom'].set_color(self.config.CHART_STYLE['text_color'])
            ax.spines['left'].set_color(self.config.CHART_STYLE['text_color'])
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            
            # Add grid for better readability
            ax.grid(True, alpha=0.3, color=self.config.CHART_STYLE['text_color'])
            ax.set_axisbelow(True)
            
            plt.tight_layout()
            plt.savefig(path, transparent=False, dpi=300, bbox_inches='tight', 
                       facecolor=fig.get_facecolor(), edgecolor='none')
            
            logger.info(f"Enhanced product sales chart saved to {path}")
            return path

        except Exception as e:
            logger.error(f"Error generating product sales chart: {e}")
            return self._create_error_chart(path, "Chart Generation Error")
        finally:
            plt.close('all')

    def _create_error_chart(self, path: str, message: str) -> str:
        """Create a simple error message chart."""
        try:
            fig, ax = plt.subplots(figsize=(8, 6), facecolor=self.config.CHART_STYLE['figure_facecolor'])
            ax.set_facecolor(self.config.CHART_STYLE['axes_facecolor'])
            ax.text(0.5, 0.5, f"⚠️ {message}", ha='center', va='center', 
                   transform=ax.transAxes, color='#ff6b6b', fontsize=16, weight='bold')
            ax.axis('off')
            plt.tight_layout()
            plt.savefig(path, transparent=False, dpi=300, bbox_inches='tight', 
                       facecolor=fig.get_facecolor())
            return path
        except Exception:
            return ""
        finally:
            plt.close('all')
    
    def _create_no_data_chart(self, path: str, message: str) -> str:
        """Create a chart indicating no data available."""
        try:
            fig, ax = plt.subplots(figsize=(8, 6), facecolor=self.config.CHART_STYLE['figure_facecolor'])
            ax.set_facecolor(self.config.CHART_STYLE['axes_facecolor'])
            ax.text(0.5, 0.5, f"📊 {message}", ha='center', va='center', 
                   transform=ax.transAxes, color=self.config.CHART_STYLE['text_color'], 
                   fontsize=14, weight='bold')
            ax.axis('off')
            plt.tight_layout()
            plt.savefig(path, transparent=False, dpi=300, bbox_inches='tight', 
                       facecolor=fig.get_facecolor())
            return path
        except Exception:
            return ""
        finally:
            plt.close('all')

class SalesReportGenerator:
    """Main class for generating comprehensive sales reports."""
    
    def __init__(self, config: SalesReportConfig = None):
        self.config = config or SalesReportConfig()
        self.chart_generator = ChartGenerator(self.config)
        self.validator = DataValidator()
    
    def generate_comprehensive_report(self, report: Dict, report_id: str, 
                                    pdf_path: str = "comprehensive_sales_report.pdf") -> str:
        """Generate a comprehensive multi-page PDF sales report with enhanced features."""
        try:
            # Validate input data
            if not self.validator.validate_report_data(report):
                logger.error("Invalid report data provided")
                return ""

            # Generate charts
            charts = self._generate_all_charts(report, report_id)
            
            # Create PDF with enhanced styling
            doc = SimpleDocTemplate(pdf_path, pagesize=A4, topMargin=50, bottomMargin=50,
                                  leftMargin=50, rightMargin=50)
            
            elements = []
            styles = self._create_enhanced_styles()
            
            # Build report sections
            elements.extend(self._create_title_section(report, report_id, styles))
            elements.extend(self._create_executive_summary(report, styles))
            elements.extend(self._create_charts_section(charts, styles))
            elements.extend(self._create_detailed_analysis(report, styles))
            elements.extend(self._create_footer_section(styles))
            
            # Build PDF
            doc.build(elements)
            logger.info(f"Comprehensive sales report generated: {pdf_path}")
            
            # Cleanup temporary files
            self._cleanup_temp_files(report_id)
            
            return pdf_path
            
        except Exception as e:
            logger.error(f"Error generating comprehensive report: {e}")
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            return ""
    
    def _generate_all_charts(self, report: Dict, report_id: str) -> Dict[str, str]:
        """Generate all required charts for the report."""
        charts = {}
        
        # Revenue chart
        revenue_path = f"revenue_{report_id}.png"
        charts['revenue'] = self.chart_generator.generate_revenue_chart(report, revenue_path)
        
        # Product sales chart
        product_path = f"products_{report_id}.png"
        charts['products'] = self.chart_generator.generate_product_sales_chart(report, product_path)
        
        return charts
    
    def _create_enhanced_styles(self) -> Dict:
        """Create enhanced PDF styles."""
        styles = getSampleStyleSheet()
        
        # Add custom styles
        styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=styles['Title'],
            fontSize=26,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#2c3e50'),
            fontName='Helvetica-Bold'
        ))
        
        styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=styles['Heading1'],
            fontSize=18,
            spaceBefore=20,
            spaceAfter=12,
            textColor=colors.HexColor('#34495e'),
            fontName='Helvetica-Bold'
        ))
        
        styles.add(ParagraphStyle(
            name='EnhancedBody',
            parent=styles['Normal'],
            fontSize=11,
            leading=16,
            spaceBefore=6,
            textColor=colors.HexColor('#2c3e50'),
            fontName='Helvetica'
        ))
        
        return styles
    
    def _create_title_section(self, report: Dict, report_id: str, styles) -> List:
        """Create the title section of the report."""
        elements = []
        
        title = f"📊 Sales Performance Report"
        subtitle = f"{report.get('report_name', f'Report #{report_id}')}"
        
        elements.append(Paragraph(title, styles['ReportTitle']))
        elements.append(Paragraph(subtitle, styles['EnhancedBody']))
        elements.append(Spacer(1, 20))
        
        # Report metadata
        generated_at = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        elements.append(Paragraph(f"<b>Generated:</b> {generated_at}", styles['EnhancedBody']))
        
        # Date range
        start_date = report.get('start_date')
        end_date = report.get('end_date')
        if start_date and end_date:
            elements.append(Paragraph(f"<b>Period:</b> {start_date} to {end_date}", styles['EnhancedBody']))
        
        elements.append(Spacer(1, 30))
        return elements
    
    def _create_executive_summary(self, report: Dict, styles) -> List:
        """Create executive summary section."""
        elements = []
        elements.append(Paragraph("Executive Summary", styles['SectionHeader']))
        
        # Calculate key metrics
        total_orders = report.get('total_orders', 0)
        total_revenue = report.get('total_revenue', 0)
        total_products = report.get('total_products_sold', 0)
        avg_order_value = total_revenue / max(total_orders, 1)
        
        # Create enhanced summary table
        summary_data = [
            ['Key Performance Indicators', 'Value', 'Status'],
            ['Total Orders', f"{total_orders:,}", self._get_status_indicator(total_orders, 100)],
            ['Total Revenue', f"${total_revenue:,.2f}", self._get_status_indicator(total_revenue, 10000)],
            ['Products Sold', f"{total_products:,}", self._get_status_indicator(total_products, 500)],
            ['Average Order Value', f"${avg_order_value:.2f}", self._get_status_indicator(avg_order_value, 50)]
        ]
        
        summary_table = Table(summary_data, colWidths=[150, 100, 80])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
            ('FONTSIZE', (0, 1), (-1, -1), 10)
        ]))
        
        elements.append(summary_table)
        elements.append(Spacer(1, 30))
        return elements
    
    def _get_status_indicator(self, value: float, threshold: float) -> str:
        """Get status indicator based on value vs threshold."""
        if value >= threshold:
            return "✅ Good"
        elif value >= threshold * 0.7:
            return "⚠️ Fair"
        else:
            return "❌ Poor"
    
    def _create_charts_section(self, charts: Dict[str, str], styles) -> List:
        """Create charts section."""
        elements = []
        
        # Revenue Analysis
        if charts.get('revenue') and os.path.exists(charts['revenue']):
            elements.append(Paragraph("Revenue Analysis", styles['SectionHeader']))
            try:
                img = Image(charts['revenue'])
                img.drawWidth = 450
                img.drawHeight = 360
                img.hAlign = 'CENTER'
                elements.append(img)
                elements.append(Spacer(1, 20))
            except Exception as e:
                logger.error(f"Could not embed revenue chart: {e}")
        
        # Product Performance
        if charts.get('products') and os.path.exists(charts['products']):
            elements.append(Paragraph("Product Performance", styles['SectionHeader']))
            try:
                img = Image(charts['products'])
                img.drawWidth = 500
                img.drawHeight = 330
                img.hAlign = 'CENTER'
                elements.append(img)
                elements.append(Spacer(1, 30))
            except Exception as e:
                logger.error(f"Could not embed product chart: {e}")
        
        return elements
    
    def _create_detailed_analysis(self, report: Dict, styles) -> List:
        """Create detailed analysis section."""
        elements = []
        elements.append(Paragraph("Detailed Analysis", styles['SectionHeader']))
        
        # Top performing category
        top_category = report.get('top_selling_category_name', 'N/A')
        if top_category != 'N/A':
            elements.append(Paragraph(f"🏆 <b>Top Performing Category:</b> {top_category}", styles['EnhancedBody']))
        
        # Revenue insights
        total_revenue = report.get('total_revenue', 0)
        if total_revenue > 0:
            elements.append(Paragraph(f"💰 <b>Revenue Performance:</b> Generated ${total_revenue:,.2f} in total sales", styles['EnhancedBody']))
        
        # Order insights
        total_orders = report.get('total_orders', 0)
        if total_orders > 0:
            avg_order = total_revenue / total_orders
            elements.append(Paragraph(f"📦 <b>Order Insights:</b> {total_orders:,} orders with average value of ${avg_order:.2f}", styles['EnhancedBody']))
        
        elements.append(Spacer(1, 30))
        return elements
    
    def _create_footer_section(self, styles) -> List:
        """Create footer section."""
        elements = []
        elements.append(Spacer(1, 50))
        elements.append(Paragraph("--- End of Report ---", styles['EnhancedBody']))
        elements.append(Paragraph("This report was automatically generated by the Enhanced Sales Analytics System", 
                                 styles['EnhancedBody']))
        return elements
    
    def _cleanup_temp_files(self, report_id: str):
        """Clean up temporary chart files."""
        temp_files = [
            f"revenue_{report_id}.png",
            f"products_{report_id}.png"
        ]
        
        for file_path in temp_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug(f"Cleaned up temporary file: {file_path}")
            except Exception as e:
                logger.warning(f"Could not remove temporary file {file_path}: {e}")

# Convenience functions for backward compatibility
def generate_comprehensive_sales_report_pdf(report: dict, report_id: str, pdf_path: str = "sales_report.pdf") -> str:
    """Generate comprehensive sales report - enhanced version."""
    generator = SalesReportGenerator()
    return generator.generate_comprehensive_report(report, report_id, pdf_path)

def generate_revenue_chart(report: dict, path: str = "revenue_chart.png") -> str:
    """Generate revenue chart - enhanced version."""
    chart_gen = ChartGenerator()
    return chart_gen.generate_revenue_chart(report, path)

def generate_product_sales_chart(report: dict, path: str = "product_sales_chart.png") -> str:
    """Generate product sales chart - enhanced version."""
    chart_gen = ChartGenerator()
    return chart_gen.generate_product_sales_chart(report, path)

# Example usage
if __name__ == "__main__":
    # Example report data
    sample_report = {
        'report_name': 'Q4 2024 Sales Report',
        'total_orders': 1250,
        'total_revenue': 85400.50,
        'total_products_sold': 3420,
        'start_date': '2024-10-01',
        'end_date': '2024-12-31',
        'revenue_by_category': {
            'Fridge Magnets': 25600.00,
            'Custom Prints': 18900.50,
            'Business Cards': 22100.00,
            'Stickers': 12400.00,
            'Photo Magnets': 6400.00
        },
        'top_products': {
            'Custom Logo Magnets': 450,
            'Business Card Set (500pc)': 320,
            'Photo Magnet 4x6': 280,
            'Promotional Stickers': 250,
            'Wedding Magnets': 180,
            'Company Logo Prints': 150
        },
        'top_selling_category_name': 'Fridge Magnets'
    }
    
    # Generate comprehensive report
    generator = SalesReportGenerator()
    result = generator.generate_comprehensive_report(sample_report, "sample_001", "enhanced_sales_report.pdf")
    
    if result:
        print(f"Enhanced sales report generated successfully: {result}")
    else:
        print("Failed to generate sales report")
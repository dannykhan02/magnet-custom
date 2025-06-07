import json
import uuid
import io
import os
from flask import request, jsonify, send_file, make_response
from flask_restful import Resource
from datetime import datetime
from model import db, Report, Order, OrderStatus, Product, Category, User, UserRole
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from sqlalchemy import func, cast, Numeric
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from decimal import Decimal

# Import the enhanced PDF utilities
from pdf_utils import (
    SalesReportGenerator, 
    ChartGenerator, 
    generate_comprehensive_sales_report_pdf,
    generate_revenue_chart,
    generate_product_sales_chart
)

# Email functionality imports
from email_utils import send_sales_report_email, EmailError, cleanup_temp_files
import tempfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ReportGenerationResource(Resource):
    """
    Resource for admins to generate and retrieve reports.
    Enhanced with better data collection for charts and analytics.
    """

    @jwt_required()
    def post(self):
        """
        Generate a new report with enhanced data collection for charts.
        Admins only.
        """
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)

        if not user or user.role != UserRole.ADMIN:
            return {"message": "Only admins can generate reports"}, 403

        data = request.get_json()
        if not data or 'report_name' not in data:
            return {"message": "Report name is required"}, 400

        report_name = data['report_name']
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')

        start_date = None
        end_date = None

        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str)
            except ValueError:
                return {"message": "Invalid start_date format. Use YYYY-MM-DDTHH:MM:SS"}, 400
        
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str)
            except ValueError:
                return {"message": "Invalid end_date format. Use YYYY-MM-DDTHH:MM:SS"}, 400

        if start_date and end_date and start_date > end_date:
            return {"message": "Start date cannot be after end date"}, 400

        try:
            # Enhanced data collection for better reporting
            enhanced_data = self._collect_enhanced_report_data(start_date, end_date)
            
            new_report = Report(
                report_name=report_name,
                start_date=start_date,
                end_date=end_date,
                total_orders=enhanced_data['total_orders'],
                total_revenue=enhanced_data['total_revenue'],
                total_products_sold=enhanced_data['total_products_sold'],
                top_selling_category_id=enhanced_data['top_selling_category_id'],
                # Store enhanced data as JSON for chart generation
                enhanced_data=json.dumps(enhanced_data['chart_data'])
            )

            db.session.add(new_report)
            db.session.commit()

            response_data = {
                "message": "Report generated successfully",
                "report_id": new_report.id,
                "report_name": new_report.report_name,
                "generated_at": new_report.generated_at.isoformat(),
                "start_date": new_report.start_date.isoformat() if new_report.start_date else None,
                "end_date": new_report.end_date.isoformat() if new_report.end_date else None,
                "total_orders": new_report.total_orders,
                "total_revenue": str(new_report.total_revenue),
                "total_products_sold": new_report.total_products_sold,
                "top_selling_category_id": new_report.top_selling_category_id
            }

            # Add category name if available
            if enhanced_data['top_selling_category_id']:
                category = Category.query.get(enhanced_data['top_selling_category_id'])
                if category:
                    response_data['top_selling_category_name'] = category.name

            return response_data, 201

        except OperationalError as e:
            db.session.rollback()
            logger.error(f"Database operational error during report generation: {str(e)}")
            return {"message": "Database connection error during report generation"}, 500
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"SQLAlchemy error during report generation: {str(e)}")
            return {"message": "An error occurred with the database during report generation"}, 500
        except Exception as e:
            db.session.rollback()
            logger.error(f"Unexpected error during report generation: {str(e)}", exc_info=True)
            return {"message": "An unexpected error occurred while generating the report"}, 500

    def _collect_enhanced_report_data(self, start_date, end_date):
        """
        Collect enhanced data for better chart generation and analytics.
        """
        # Base query for delivered orders
        query = Order.query.filter_by(status=OrderStatus.DELIVERED)
        
        if start_date:
            query = query.filter(Order.order_date >= start_date)
        if end_date:
            query = query.filter(Order.order_date <= end_date)

        orders = query.all()
        total_orders = len(orders)
        total_revenue = sum(order.total_amount for order in orders)
        
        # Enhanced data collection
        category_revenue = {}
        category_quantities = {}
        product_sales = {}
        total_products_sold = 0
        
        for order in orders:
            for item in order.order_items:  # Assuming 'order_items' relationship
                product = Product.query.get(item.product_id)
                if product:
                    # Product sales tracking
                    product_name = product.name
                    product_sales[product_name] = product_sales.get(product_name, 0) + item.quantity
                    total_products_sold += item.quantity
                    
                    # Category tracking
                    if product.category_id:
                        category = Category.query.get(product.category_id)
                        if category:
                            category_name = category.name
                            # Revenue by category
                            item_revenue = float(item.quantity * item.unit_price)
                            category_revenue[category_name] = category_revenue.get(category_name, 0) + item_revenue
                            # Quantity by category
                            category_quantities[category_name] = category_quantities.get(category_name, 0) + item.quantity

        # Find top selling category
        top_selling_category_id = None
        if category_quantities:
            top_category_name = max(category_quantities, key=category_quantities.get)
            # Get category ID for database storage
            top_category = Category.query.filter_by(name=top_category_name).first()
            if top_category:
                top_selling_category_id = top_category.id

        # Prepare chart data
        chart_data = {
            'revenue_by_category': category_revenue,
            'top_products': dict(sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:20]),
            'category_quantities': category_quantities,
            'total_orders': total_orders,
            'total_revenue': float(total_revenue),
            'total_products_sold': total_products_sold,
            'top_selling_category_name': max(category_quantities, key=category_quantities.get) if category_quantities else None
        }

        return {
            'total_orders': total_orders,
            'total_revenue': Decimal(str(total_revenue)),
            'total_products_sold': total_products_sold,
            'top_selling_category_id': top_selling_category_id,
            'chart_data': chart_data
        }

    @jwt_required()
    def get(self, report_id=None):
        """
        Retrieve a specific report by ID or list all generated reports.
        Admins only.
        """
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)

        if not user or user.role != UserRole.ADMIN:
            return {"message": "Only admins can view reports"}, 403

        try:
            if report_id:
                report = Report.query.get(report_id)
                if not report:
                    return {"message": "Report not found"}, 404
                
                report_data = {
                    "id": report.id,
                    "report_name": report.report_name,
                    "generated_at": report.generated_at.isoformat(),
                    "start_date": report.start_date.isoformat() if report.start_date else None,
                    "end_date": report.end_date.isoformat() if report.end_date else None,
                    "total_orders": report.total_orders,
                    "total_revenue": str(report.total_revenue),
                    "total_products_sold": report.total_products_sold,
                    "top_selling_category_id": report.top_selling_category_id
                }
                
                # Add enhanced data if available
                if hasattr(report, 'enhanced_data') and report.enhanced_data:
                    try:
                        enhanced_data = json.loads(report.enhanced_data)
                        report_data['chart_preview'] = {
                            'categories_count': len(enhanced_data.get('revenue_by_category', {})),
                            'top_products_count': len(enhanced_data.get('top_products', {})),
                            'has_chart_data': True
                        }
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid enhanced_data JSON for report {report_id}")
                
                # Add top selling category name
                if report.top_selling_category_id:
                    category = Category.query.get(report.top_selling_category_id)
                    if category:
                        report_data['top_selling_category_name'] = category.name

                return report_data, 200
            else:
                page = request.args.get('page', 1, type=int)
                per_page = request.args.get('per_page', 10, type=int)
                
                reports = Report.query.order_by(Report.generated_at.desc()).paginate(
                    page=page, per_page=per_page, error_out=False
                )

                if not reports.items:
                    return {
                        'reports': [],
                        'total': 0,
                        'pages': 0,
                        'current_page': page
                    }, 200
                
                reports_data = []
                for report in reports.items:
                    report_dict = {
                        "id": report.id,
                        "report_name": report.report_name,
                        "generated_at": report.generated_at.isoformat(),
                        "start_date": report.start_date.isoformat() if report.start_date else None,
                        "end_date": report.end_date.isoformat() if report.end_date else None,
                        "total_orders": report.total_orders,
                        "total_revenue": str(report.total_revenue),
                        "total_products_sold": report.total_products_sold,
                        "top_selling_category_id": report.top_selling_category_id
                    }
                    if report.top_selling_category_id:
                        category = Category.query.get(report.top_selling_category_id)
                        if category:
                            report_dict['top_selling_category_name'] = category.name
                    reports_data.append(report_dict)

                return {
                    'reports': reports_data,
                    'total': reports.total,
                    'pages': reports.pages,
                    'current_page': reports.page
                }, 200

        except OperationalError as e:
            logger.error(f"Database operational error during report retrieval: {str(e)}")
            return {"message": "Database connection error during report retrieval"}, 500
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy error during report retrieval: {str(e)}")
            return {"message": "An error occurred with the database during report retrieval"}, 500
        except Exception as e:
            logger.error(f"Unexpected error during report retrieval: {str(e)}", exc_info=True)
            return {"message": "An unexpected error occurred while retrieving reports"}, 500


class ReportPDFResource(Resource):
    """
    Enhanced PDF resource using the new pdf_utils for comprehensive reports.
    """

    @jwt_required()
    def get(self, report_id):
        """
        Download a comprehensive enhanced report as PDF.
        Admins only.
        """
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)

        if not user or user.role != UserRole.ADMIN:
            return {"message": "Only admins can download reports"}, 403

        try:
            report = Report.query.get(report_id)
            if not report:
                return {"message": "Report not found"}, 404

            # Prepare comprehensive report data
            report_data = self._prepare_comprehensive_report_data(report)
            
            # Generate enhanced PDF using pdf_utils
            pdf_filename = f"enhanced_report_{report.report_name.replace(' ', '_')}_{report.id}.pdf"
            temp_pdf_path = os.path.join(tempfile.gettempdir(), pdf_filename)
            
            # Use the enhanced PDF generator
            generator = SalesReportGenerator()
            result_path = generator.generate_comprehensive_report(
                report_data, 
                str(report.id), 
                temp_pdf_path
            )
            
            if not result_path or not os.path.exists(result_path):
                return {"message": "Failed to generate PDF report"}, 500
            
            # Read the generated PDF
            with open(result_path, 'rb') as pdf_file:
                pdf_buffer = io.BytesIO(pdf_file.read())
            
            # Clean up temporary file
            try:
                os.remove(result_path)
            except Exception as e:
                logger.warning(f"Could not remove temporary PDF file: {e}")
            
            return send_file(
                pdf_buffer,
                as_attachment=True,
                download_name=pdf_filename,
                mimetype='application/pdf'
            )

        except Exception as e:
            logger.error(f"Error generating enhanced PDF report: {str(e)}", exc_info=True)
            return {"message": "An error occurred while generating the enhanced PDF report"}, 500

    def _prepare_comprehensive_report_data(self, report):
        """
        Prepare comprehensive data for the enhanced PDF generator.
        """
        report_data = {
            'report_name': report.report_name,
            'total_orders': report.total_orders,
            'total_revenue': float(report.total_revenue),
            'total_products_sold': report.total_products_sold,
            'start_date': report.start_date.strftime('%Y-%m-%d') if report.start_date else None,
            'end_date': report.end_date.strftime('%Y-%m-%d') if report.end_date else None,
            'top_selling_category_name': None
        }
        
        # Add top selling category name
        if report.top_selling_category_id:
            category = Category.query.get(report.top_selling_category_id)
            if category:
                report_data['top_selling_category_name'] = category.name
        
        # Add enhanced data if available
        if hasattr(report, 'enhanced_data') and report.enhanced_data:
            try:
                enhanced_data = json.loads(report.enhanced_data)
                report_data.update({
                    'revenue_by_category': enhanced_data.get('revenue_by_category', {}),
                    'top_products': enhanced_data.get('top_products', {}),
                    'category_quantities': enhanced_data.get('category_quantities', {})
                })
            except json.JSONDecodeError:
                logger.warning(f"Could not parse enhanced_data for report {report.id}")
        
        return report_data


class ReportEmailResource(Resource):
    """
    Enhanced email resource using the new PDF generation capabilities.
    """

    @jwt_required()
    def post(self, report_id):
        """
        Send an enhanced report via email as PDF attachment.
        Admins only.
        """
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)

        if not user or user.role != UserRole.ADMIN:
            return {"message": "Only admins can send reports"}, 403

        data = request.get_json()
        if not data or 'recipient_email' not in data:
            return {"message": "Recipient email is required"}, 400

        recipient_email = data['recipient_email']
        sender_email = data.get('sender_email')

        temp_file = None
        
        try:
            report = Report.query.get(report_id)
            if not report:
                return {"message": "Report not found"}, 404

            # Prepare comprehensive report data
            pdf_resource = ReportPDFResource()
            report_data = pdf_resource._prepare_comprehensive_report_data(report)
            
            # Generate enhanced PDF
            generator = SalesReportGenerator()
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            temp_file.close()
            
            result_path = generator.generate_comprehensive_report(
                report_data, 
                str(report.id), 
                temp_file.name
            )
            
            if not result_path or not os.path.exists(result_path):
                return {"message": "Failed to generate PDF for email"}, 500
            
            # Send email using email_utils
            success = send_sales_report_email(
                recipient=recipient_email,
                report_name=report.report_name,
                pdf_path=result_path,
                report_data=report_data,
                sender=sender_email
            )
            
            if success:
                return {
                    "message": "Enhanced report sent successfully",
                    "recipient": recipient_email,
                    "report_name": report.report_name,
                    "sent_at": datetime.now().isoformat(),
                    "report_type": "Enhanced PDF with Charts"
                }, 200
            else:
                return {"message": "Failed to send email"}, 500

        except EmailError as e:
            logger.error(f"Email error: {str(e)}")
            return {"message": f"Email error: {str(e)}"}, 500
        except Exception as e:
            logger.error(f"Error sending enhanced report email: {str(e)}", exc_info=True)
            return {"message": "An error occurred while sending the enhanced report email"}, 500
        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file.name):
                cleanup_temp_files([temp_file.name])


# New resource for chart generation endpoints
class ReportChartsResource(Resource):
    """
    Resource for generating individual charts from reports.
    """

    @jwt_required()
    def get(self, report_id, chart_type):
        """
        Generate and return individual charts for a report.
        Supported chart types: 'revenue', 'products'
        """
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)

        if not user or user.role != UserRole.ADMIN:
            return {"message": "Only admins can generate charts"}, 403

        if chart_type not in ['revenue', 'products']:
            return {"message": "Invalid chart type. Supported: 'revenue', 'products'"}, 400

        try:
            report = Report.query.get(report_id)
            if not report:
                return {"message": "Report not found"}, 404

            # Prepare report data
            pdf_resource = ReportPDFResource()
            report_data = pdf_resource._prepare_comprehensive_report_data(report)
            
            # Generate specific chart
            chart_generator = ChartGenerator()
            temp_chart_path = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
            temp_chart_path.close()
            
            if chart_type == 'revenue':
                result_path = chart_generator.generate_revenue_chart(report_data, temp_chart_path.name)
            else:  # products
                result_path = chart_generator.generate_product_sales_chart(report_data, temp_chart_path.name)
            
            if not result_path or not os.path.exists(result_path):
                return {"message": f"Failed to generate {chart_type} chart"}, 500
            
            # Return the chart image
            with open(result_path, 'rb') as chart_file:
                chart_buffer = io.BytesIO(chart_file.read())
            
            # Clean up
            try:
                os.remove(result_path)
            except Exception as e:
                logger.warning(f"Could not remove temporary chart file: {e}")
            
            return send_file(
                chart_buffer,
                as_attachment=True,
                download_name=f"{chart_type}_chart_{report_id}.png",
                mimetype='image/png'
            )

        except Exception as e:
            logger.error(f"Error generating {chart_type} chart: {str(e)}", exc_info=True)
            return {"message": f"An error occurred while generating the {chart_type} chart"}, 500


def register_report_resources(api):
    """Registers the enhanced Report resource routes with Flask-RESTful API."""
    api.add_resource(ReportGenerationResource, "/admin/reports", "/admin/reports/<string:report_id>")
    api.add_resource(ReportPDFResource, "/admin/reports/<string:report_id>/download")
    api.add_resource(ReportEmailResource, "/admin/reports/<string:report_id>/email")
    api.add_resource(ReportChartsResource, "/admin/reports/<string:report_id>/charts/<string:chart_type>")
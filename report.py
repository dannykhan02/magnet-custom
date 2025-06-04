import json
import uuid
from flask import request, jsonify
from flask_restful import Resource
from datetime import datetime
from model import db, Report, Order, OrderStatus, Product, Category, User, UserRole
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from sqlalchemy import func, cast, Numeric
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from decimal import Decimal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ReportGenerationResource(Resource):
    """
    Resource for admins to generate and retrieve reports.
    """

    @jwt_required()
    def post(self):
        """
        Generate a new report.
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
            # Calculate report metrics based on orders within the date range
            query = Order.query.filter_by(status=OrderStatus.DELIVERED)
            
            if start_date:
                query = query.filter(Order.order_date >= start_date)
            if end_date:
                query = query.filter(Order.order_date <= end_date)

            total_orders = query.count()
            total_revenue = query.with_entities(func.sum(Order.total_amount)).scalar()
            
            # Calculate total products sold and top selling category
            total_products_sold = 0
            top_selling_category_id = None
            
            # This part assumes Order has a relationship to OrderItem and Product for detailed calculations.
            # For simplicity, we'll iterate through orders and their items.
            # In a real-world scenario, you might want more optimized SQL queries.
            category_sales = {}
            for order in query.all():
                for item in order.order_items:  # Assuming 'order_items' relationship in Order model
                    total_products_sold += item.quantity
                    product = Product.query.get(item.product_id)
                    if product and product.category_id:
                        category_sales[product.category_id] = category_sales.get(product.category_id, 0) + item.quantity
            
            if category_sales:
                top_selling_category_id = max(category_sales, key=category_sales.get)

            # Ensure total_revenue is a Decimal
            total_revenue = Decimal(total_revenue) if total_revenue else Decimal('0.00')

            new_report = Report(
                report_name=report_name,
                start_date=start_date,
                end_date=end_date,
                total_orders=total_orders,
                total_revenue=total_revenue,
                total_products_sold=total_products_sold,
                top_selling_category_id=top_selling_category_id
            )

            db.session.add(new_report)
            db.session.commit()

            return {
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
            }, 201

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
                # Optionally, fetch top selling category name
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


def register_report_resources(api):
    """Registers the Report resource routes with Flask-RESTful API."""
    api.add_resource(ReportGenerationResource, "/admin/reports", "/admin/reports/<string:report_id>")